# coding: utf-8

import os
from time import time_ns

import requests
from huaweicloudsdkcore.auth.credentials import BasicCredentials
from huaweicloudsdkdns.v2 import *
from huaweicloudsdkdns.v2.region.dns_region import DnsRegion

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


def get_text_ips(url):
    ips = []
    resp = requests.get(url).text
    for ip in resp.split("\n"):
        ips.append(ip)
    return ips


def get_doh_ips(name):
    ips = []
    resp = requests.get("https://doh.pub/dns-query?type=1&name=" + name).json()
    for answer in resp["Answer"]:
        ip = answer["data"]
        ips.append(ip)
    return ips


def get_recordset_ips(recordset):
    ips = []
    if recordset is not None:
        for record in recordset.records:
            ips.append(record)
    return ips


def filter_ips(ips):
    print(ips)
    ip_set = set()
    for ip in ips:
        if len(ip_set) >= 256:
            break
        organization = asn_reader.asn(ip).autonomous_system_organization
        if organization.startswith("Alibaba"):
            country = city_reader.city(ip).country.iso_code
            if country == "SG" or country == "HK":
                ip_set.add(ip)
    return ip_set


def get_ip_info(ip):
    url = "http://" + ip
    headers = {"host": "www.cloudflare.com"}
    try:
        start_time = time_ns()
        res = requests.get(url=url, headers=headers, timeout=2)
        end_time = time_ns()

        latency = (end_time - start_time) / 1_000_000

        response = city_reader.city(ip)

        print(f"请求 {response.country.iso_code} {ip} 响应时间 {latency}ms")

        return {
            'ip': ip,
            'status': res.status_code == 200,
            'latency': latency
        }
    except Exception as e:
        return {
            'ip': ip,
            'status': False
        }


if __name__ == "__main__":

    zone = get_zone(zone_name)

    recordset = get_recordset(zone.id, recordset_name)

    recordset_ips = get_recordset_ips(recordset)

    hk_ips = get_doh_ips("hk.921219.xyz")

    proxy_ips = get_text_ips("https://ipdb.api.030101.xyz/?type=bestproxy&country=false")

    ips = filter_ips(recordset_ips + hk_ips + proxy_ips)

    print(f'本次获取IP数量{len(ips)}个')

    ips_info = []

    for ip in ips:
        ips_info.append(get_ip_info(ip))

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
