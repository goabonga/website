#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>
"""Create or update wildcard CNAME records in Route 53.

usage: route53_wildcard_cname.py --target TARGET NAME [NAME ...]

Each NAME (for example *.auth.example.com) gets a CNAME pointing to TARGET in
the hosted zone that contains it. Prints CREATED, OK or SKIP lines.
"""

import argparse
import sys

import boto3


def find_zone(zones, name):
    parts = name.lstrip("*.").split(".")
    for index in range(len(parts)):
        candidate = ".".join(parts[index:]) + "."
        for zone in zones:
            if zone["Name"] == candidate:
                return zone["Id"].split("/")[-1]
    return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", required=True)
    parser.add_argument("names", nargs="+")
    args = parser.parse_args()

    target = args.target if args.target.endswith(".") else args.target + "."
    client = boto3.client("route53")
    zones = client.list_hosted_zones()["HostedZones"]

    for name in args.names:
        zone_id = find_zone(zones, name)
        if not zone_id:
            print(f"SKIP: no hosted zone for {name}")
            continue
        fqdn = name if name.endswith(".") else name + "."
        response = client.list_resource_record_sets(
            HostedZoneId=zone_id, StartRecordName=fqdn, StartRecordType="CNAME", MaxItems="1"
        )
        records = response.get("ResourceRecordSets", [])
        if (
            records
            and records[0].get("Name") == fqdn
            and records[0].get("Type") == "CNAME"
            and target in [r["Value"] for r in records[0].get("ResourceRecords", [])]
        ):
            print(f"OK: {name} -> {target}")
            continue
        client.change_resource_record_sets(
            HostedZoneId=zone_id,
            ChangeBatch={
                "Comment": f"Wildcard CNAME for {name} (managed by Ansible)",
                "Changes": [
                    {
                        "Action": "UPSERT",
                        "ResourceRecordSet": {
                            "Name": fqdn,
                            "Type": "CNAME",
                            "TTL": 300,
                            "ResourceRecords": [{"Value": target}],
                        },
                    }
                ],
            },
        )
        print(f"CREATED: {name} -> {target}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
