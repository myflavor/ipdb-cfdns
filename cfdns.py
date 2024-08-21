# coding: utf-8

import os
from time import time_ns

import requests
from huaweicloudsdkcore.auth.credentials import BasicCredentials
from huaweicloudsdkdns.v2 import *
from huaweicloudsdkdns.v2.region.dns_region import DnsRegion
from concurrent.futures import ThreadPoolExecutor, as_completed

import geoip2.database

city_reader = geoip2.database.Reader('GeoLite2-City.mmdb')
asn_reader = geoip2.database.Reader('GeoLite2-ASN.mmdb')

ak = os.environ["CLOUD_SDK_AK"]
sk = os.environ["CLOUD_SDK_SK"]
client_region = os.environ["CLIENT_REGION"]
zone_name = os.environ["ZONE_NAME"]
recordset_name = os.environ["RECORDSET_NAME"]

credentials = BasicCredentials(ak, sk)

client = DnsClient.new_builder() \
    .with_credentials(credentials) \
    .with_region(DnsRegion.value_of(client_region)) \
    .build()


def get_zone(name):
    request = ListPublicZonesRequest()
    response = client.list_public_zones(request)
    for zone in response.zones:
        if zone.name == name:
            return zone


def get_recordset(zone_id, name):
    request = ListRecordSetsByZoneRequest()
    request.zone_id = zone_id
    response = client.list_record_sets_by_zone(request)
    for recordset in response.recordsets:
        if recordset.name == name:
            return recordset


def update_recordset(recordset, records):
    request = UpdateRecordSetRequest()
    request.zone_id = recordset.zone_id
    request.recordset_id = recordset.id
    request.body = UpdateRecordSetReq(
        records=records,
        type=recordset.type,
        name=recordset.name
    )
    response = client.update_record_set(request)
    return response


def create_recordset(zone_id, name, records):
    request = CreateRecordSetRequest()
    request.zone_id = zone_id
    request.body = CreateRecordSetRequestBody(
        records=records,
        type="A",
        name=name
    )
    response = client.create_record_set(request)
    return response


def get_proxy_ips():
    resp = requests.get("https://ipdb.api.030101.xyz/?type=proxy&country=false").text
    ips = set()
    for ip in resp.split("\n"):
        if len(ips) > 256:
            break
        country = city_reader.city(ip).country.iso_code
        organization = asn_reader.asn(ip).autonomous_system_organization
        if country == "HK" or country == "SG":
            if organization.startswith("Alibaba"):
                ips.add(ip)
    print(f'本次获取IP数量{len(ips)}个')
    return ips


def get_ip_info(ip):
    url = "http://" + ip
    headers = {"host": "www.cloudflare.com"}

    latency = 0
    test_times = 2
    for _ in range(test_times):
        try:
            start_time = time_ns()
            res = requests.get(url=url, headers=headers, timeout=2)
            end_time = time_ns()
            elapsed_time = int((end_time - start_time) / 1_000_000)

            if res.status_code == 200:
                latency += elapsed_time
            else:
                raise Exception
        except:
            return {
                'ip': ip,
                'status': False
            }

    latency /= test_times

    response = city_reader.city(ip)

    print(f"请求 {response.country.iso_code} {ip} 响应时间 {latency}ms")

    return {
        'ip': ip,
        'status': True,
        'latency': latency
    }


if __name__ == "__main__":

    proxy_ips = get_proxy_ips()

    zone = get_zone(zone_name)

    recordset = get_recordset(zone.id, recordset_name)

    ips_info = []

    with ThreadPoolExecutor(max_workers=8) as executor:
        future_to_ip = {executor.submit(get_ip_info, ip): ip for ip in proxy_ips}
        for future in as_completed(future_to_ip):
            ip_info = future.result()
            ips_info.append(ip_info)

    best_ips_info = sorted([ip for ip in ips_info if ip['status']], key=lambda x: x['latency'])[:8]

    best_ips = []

    for ip_info in best_ips_info:
        if len(best_ips) > 8:
            break
        best_ips.append(ip_info['ip'])

    if recordset is None:
        create_recordset(zone.id, recordset_name, best_ips)
        print(f"创建记录 {best_ips}")
    else:
        update_recordset(recordset, best_ips)
        print(f"更新记录 {best_ips}")
