#!/usr/bin/env python3

""" uses canhazip to pull the public IP and update cloudflare DNS """

from pathlib import Path
import socket
import sys
from typing import Any, Dict, List, Optional

try:
    import requests
    import requests.exceptions
    from loguru import logger
    import loguru._logger
except ImportError as import_error:
    sys.exit(f"Failed to import  {import_error}")


def setup_logging(
    logger_object: loguru._logger.Logger=logger,
    debug: bool=False
    ) -> None:
    """ handles logging configuration """
    if debug:
        logger_object.remove()
        logger_object.add(sys.stdout, level="DEBUG")
    else:
        logger_object.remove()
        logger_object.add(sys.stdout, level="INFO")

def get_zoneid(
    zone_name: str,
    auth_headers: Dict[str,str],
    ) -> Optional[str]:
    """ pulls the data for a given zone

    API documentation: https://api.cloudflare.com/#zone-zone-details
    """
    url = f"https://api.cloudflare.com/client/v4/zones?name={zone_name}&status=active"

    try:
        response = requests.get(url=url, headers=auth_headers)
        response.raise_for_status()
    except requests.exceptions.HTTPError as error_message:
        logger.error("Failed to get zoneID: {}", error_message)
        return None
    zoneid = ""
    data = response.json()
    for zone in data.get('result'):
        if zone.get('name') == 'yaleman.org':
            zoneid = zone.get('id')
    if zoneid:
        return zoneid
    logger.error("Zone ID not found for zone {}", zone_name)
    return None

def get_dns_record_data(
    zoneid: str,
    auth_headers: Dict[str,str],
    name: str,
    type_name: str,
    ) -> Dict[str, Any]:
    """ pulls the data for a given record, you can pass different search filters

    API documentation: https://api.cloudflare.com/#dns-records-for-a-zone-list-dns-records
    """
    url = f"https://api.cloudflare.com/client/v4/zones/{zoneid}/dns_records"
    try:
        response = requests.get(url=url,
                            headers=auth_headers,
                            params={
                                "name" : name,
                                "type_name" : type_name,
                            },
                            )

        response.raise_for_status()
    except requests.exceptions.HTTPError as error_message:
        logger.error("Failed to get dns record data for {}: {}", zoneid, error_message)
    result: Dict[str, Any] = response.json()
    return result

def get_dns_record_id(
    zoneid: str,
    auth_headers: Dict[str,str],
    name: str,
    type_name: str,
    ) -> Optional[str]:
    """ looks for a dns record
    API documentation: https://api.cloudflare.com/#dns-records-for-a-zone-list-dns-records
    """
    data = get_dns_record_data(
        zoneid=zoneid,
        auth_headers=auth_headers,
        name=name,
        type_name=type_name,
        )

    if "result" not in data:
        logger.error("Record not found for {}", name)
        return None
    for record in data["result"]:
        foundit = True
        if "name" not in record:
            foundit = False
        if foundit:
            return str(record['id'])
    return None


# pylint: disable=too-many-arguments
def update_zone_record(
    zoneid: str,
    recordid: str,
    name: str,
    auth_headers: Dict[str,str],
    content: str,
    type_name: str="A",
    ttl: int=1,
    proxied: bool=False,
    ) -> Optional[Dict[str, Any]]:
    """ API documentation: https://api.cloudflare.com/#dns-records-for-a-zone-update-dns-record """

    url = f"https://api.cloudflare.com/client/v4/zones/{zoneid}/dns_records/{recordid}"
    data = {
        "name" : name,
        "type" : type_name,
        "content" : content,
        "ttl": ttl,
        "proxied": proxied,
    }
    response = requests.put(url=url, json=data, headers=auth_headers)
    try:
        response.raise_for_status()
        result: Dict[str, Any] = response.json()
        return result
    except requests.exceptions.HTTPError:
        logger.error("Error raised:")
        logger.error("Request body: {}", response.request.body)
        logger.error("Response body: {}", response.text)
    return None


def grabhazip(try_no: int=0) -> Optional[str]:
    """ query canhazip.com for our public IP """
    if try_no >= 10:
        return None
    response = requests.get('http://ipv4.icanhazip.com')
    response.raise_for_status()
    ip_address = response.text.strip()
    logger.debug("IP is {}", ip_address)
    try:
        logger.debug("Trying to parse {}", ip_address)
        socket.inet_aton(ip_address)
    except socket.error:
        logger.error("Failed to parse this as an ip '{}', quitting.", ip_address)
        return None
    except Exception: #pylint: disable=broad-except
        return grabhazip(try_no+1)
    logger.debug("Returning {}", ip_address)
    return ip_address


# pylint: disable=too-many-branches
def cli(auth_headers: Dict[str, str]) -> None:
    """ command line interface """
    logger.debug("getting zoneid for yaleman.org")
    zoneid = get_zoneid(zone_name='yaleman.org', auth_headers=auth_headers)
    if zoneid is None:
        logger.error("Couldn't get ZoneID, bailing.")
        return
    logger.debug("getting dns record data for azerbaijan")
    record = get_dns_record_data(zoneid,
                                 name='azerbaijan.yaleman.org',
                                 type_name='A',
                                 auth_headers=auth_headers,
                                 )
    logger.debug("getting dns record id for azerbaijan")
    recordid = get_dns_record_id(zoneid,
                                 name='azerbaijan.yaleman.org',
                                 type_name="A",
                                 auth_headers=auth_headers,
                                 )

    if recordid is None:
        logger.debug("Bailing - couldn't get record ID")
        return
    if record is None or "result" not in record:
        logger.debug("Bailing")
        return

    result: List[Dict[str,str]] = record["result"]
    if len(result) == 1:
        current_ip = result[0]["content"]
        logger.debug("Current IP: '{}'", current_ip)

        if len(sys.argv) > 1:
            logger.debug("Got this as an IP on the commandline: {}",
                         sys.argv[1].strip(),
                         )
            ip_address: str = sys.argv[1].strip()
        else:
            grab_ip = grabhazip()

            if grab_ip is None:
                return
            ip_address = grab_ip
        try:
            socket.inet_aton(ip_address)
        except socket.error:
            logger.debug("Failed to parse this as an ip '{}', quitting.", ip_address)
            return

        if current_ip != ip_address:
            logger.debug("Updating record, new IP: {}", ip_address)
            update_result = update_zone_record(zoneid=zoneid,
                                        recordid=recordid,
                                        content=ip_address,
                                        name='azerbaijan.yaleman.org',
                                        auth_headers=auth_headers,
                                        )

            if update_result is None:
                return
            if update_result.get('success') is not None:
                logger.info("Successful: {}", update_result["success"])
            else:
                logger.error("Failed to update: old: {} new:{} - {}",
                             current_ip,
                             ip_address,
                             update_result,
                             )
        else:
            logger.info("No change required")

def main() -> None:
    """ main func """
    config_files = [
        "~/update_dns.conf",
        "/etc/update_dns.conf",
        "/data/update_dns.conf",
        ]
    for filename in config_files:
        config_filename = Path(filename).expanduser().resolve()
        if config_filename.exists():
            auth_headers_dict = {
                'Authorization' : f"Bearer {config_filename.open(encoding='utf-8').read().strip()}",
                'Content-Type' : 'application/json',
            }

            setup_logging(logger, False)
            cli(auth_headers=auth_headers_dict)
            sys.exit(0)
    logger.error("Couldn't find configuration file, looked in: {}", ",".join(config_files))

if __name__ == '__main__':
    main()
