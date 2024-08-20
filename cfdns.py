# coding: utf-8

import os
from time import time_ns

import requests
from huaweicloudsdkcore.auth.credentials import BasicCredentials
from huaweicloudsdkdns.v2 import *
from huaweicloudsdkdns.v2.region.dns_region import DnsRegion

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
    resp = requests.get("https://ipdb.api.030101.xyz/?type=bestproxy&country=false").text
    ips = set()
    for ip in resp.split("\n"):
        ips.add(ip)
    return ips


def filter_best_ips(ips):
    result = []
    for ip in ips:
        url = "http://" + ip
        headers = {"host": "www.cloudflare.com"}
        try:
            start_time = time_ns()
            res = requests.get(url=url, headers=headers)
            end_time = time_ns()
            elapsed_time = (end_time - start_time) / 1_000_000
            if res.status_code == 200 and elapsed_time < 1000:
                result.append(ip)
        except:
            continue
    return result


if __name__ == "__main__":

    proxy_ips = get_proxy_ips()

    zone = get_zone(zone_name)
    recordset = get_recordset(zone.id, recordset_name)

    if recordset is not None:
        for record in recordset.records:
            if len(proxy_ips) > 8:
                break
            proxy_ips.add(record)

    best_ips = filter_best_ips(proxy_ips)

    if recordset is None:
        create_recordset(zone.id, recordset_name, best_ips)
        print(f"创建记录 {best_ips}")
    else:
        update_recordset(recordset, best_ips)
        print(f"更新记录 {best_ips}")
