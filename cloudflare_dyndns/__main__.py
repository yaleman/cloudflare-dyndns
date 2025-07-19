#!/usr/bin/env python3

"""uses canhazip to pull the public IP and update cloudflare DNS"""

import os
from pathlib import Path
import socket
import sys
from typing import Any, Dict, List, Optional

from . import ConfigFile

try:
    import backoff
    import requests
    import requests.exceptions
    from loguru import logger
except ImportError as import_error:
    sys.exit(f"Failed to import  {import_error}")


def setup_logging(logger_object: Any = logger, debug: bool = False) -> None:
    """handles logging configuration"""
    if debug:
        logger_object.remove()
        logger_object.add(sys.stdout, level="DEBUG")
    else:
        logger_object.remove()
        logger_object.add(sys.stdout, level="INFO")


def get_zoneid(config: ConfigFile) -> Optional[str]:
    """pulls the data for a given zone

    API documentation: https://api.cloudflare.com/#zone-zone-details
    """
    url = f"https://api.cloudflare.com/client/v4/zones?name={config.zone}&status=active"

    try:
        response = requests.get(url=url, headers=config.auth_headers(), timeout=30)
        response.raise_for_status()
    except requests.exceptions.HTTPError as error_message:
        logger.error("Failed to get zoneID: {}", error_message)
        return None
    data = response.json()
    for zone in data.get("result"):
        if zone.get("name") == config.zone:
            if "id" in zone:
                return str(zone["id"])
    logger.error("Zone ID not found for zone {}", config.zone)
    return None


def get_dns_record_data(
    config: ConfigFile,
    zoneid: str,
    name: str,
    type_name: str,
) -> Dict[str, Any]:
    """pulls the data for a given record, you can pass different search filters

    API documentation: https://api.cloudflare.com/#dns-records-for-a-zone-list-dns-records
    """
    url = f"https://api.cloudflare.com/client/v4/zones/{zoneid}/dns_records"
    try:
        response = requests.get(
            url=url,
            headers=config.auth_headers(),
            params={
                "name": name,
                "type_name": type_name,
            },
            timeout=30,
        )

        response.raise_for_status()
    except requests.exceptions.HTTPError as error_message:
        logger.error("Failed to get dns record data for {}: {}", zoneid, error_message)
    result: Dict[str, Any] = response.json()
    return result


def get_dns_record_id(
    config: ConfigFile,
    zoneid: str,
    name: str,
    type_name: str,
) -> Optional[str]:
    """looks for a dns record
    API documentation: https://api.cloudflare.com/#dns-records-for-a-zone-list-dns-records
    """
    data = get_dns_record_data(
        config=config,
        zoneid=zoneid,
        name=name,
        type_name=type_name,
    )

    if "result" not in data:
        logger.error(
            "Error getting record data for name={} errors={}",
            name,
            data["errors"],
        )
        return None
    for record in data["result"]:
        foundit = True
        if "name" not in record:
            foundit = False
        if foundit:
            logger.debug("Found result: {}", record)
            return str(record["id"])
    logger.error("Couldn't find name={} type={}", name, type_name)
    return None


# pylint: disable=too-many-arguments
def update_zone_record(
    config: ConfigFile,
    zoneid: str,
    recordid: str,
    name: str,
    content: str,
    type_name: str = "A",
    ttl: int = 1,
    proxied: bool = False,
) -> Optional[Dict[str, Any]]:
    """API documentation: https://api.cloudflare.com/#dns-records-for-a-zone-update-dns-record"""

    url = f"https://api.cloudflare.com/client/v4/zones/{zoneid}/dns_records/{recordid}"
    data = {
        "name": name,
        "type": type_name,
        "content": content,
        "ttl": ttl,
        "proxied": proxied,
    }
    if config.dry_run:
        logger.info("Would have updated {} to {}", name, content)
        return None
    response = requests.put(
        url=url, json=data, headers=config.auth_headers(), timeout=30
    )
    try:
        response.raise_for_status()
        result: Dict[str, Any] = response.json()
        return result
    except requests.exceptions.HTTPError:
        logger.error("Error raised:")
        logger.error("Request body: {}", response.request.body)
        logger.error("Response body: {}", response.text)
    return None


@backoff.on_exception(
    backoff.expo,
    Exception,
    max_time=60,
    max_tries=10,
)
def grabhazip() -> Optional[str]:
    """query canhazip.com for our public IP"""
    response = requests.get(
        "http://ipv4.icanhazip.com",
        timeout=30,
        allow_redirects=False,
    )
    if response.status_code >= 400:
        logger.error("Got {} from ipv4.canhazip.com, bailing", response.status_code)
        return None
    # response.raise_for_status()
    ip_address = response.text.strip()
    logger.debug("IP is {}", ip_address)
    try:
        logger.debug("Trying to parse {}", ip_address)
        socket.inet_aton(ip_address)
    except socket.error:
        logger.error("Failed to parse this as an ip '{}', quitting.", ip_address)
        return None
    logger.debug("Returning {}", ip_address)

    try:
        socket.inet_aton(ip_address)
    except socket.error:
        logger.debug("Failed to parse this as an ip '{}', quitting.", ip_address)
        return None
    return ip_address


# pylint: disable=too-many-branches
def cli(config: ConfigFile) -> None:
    """command line interface"""
    logger.debug("getting zoneid for {}", config.zone)
    zoneid = get_zoneid(config)
    if zoneid is None:
        logger.error("Couldn't get ZoneID, bailing.")
        return
    logger.debug("getting dns record data for {}", config.hostname)

    record = get_dns_record_data(
        config,
        zoneid,
        name=config.hostname,
        type_name="A",
    )
    if record is None or "result" not in record:
        logger.error("Bailing - record was None or 'result' not in record!")
        logger.debug("Result: {}", record)
        return
    else:
        logger.debug("got result: {}", record)

    result: List[Dict[str, str]] = record["result"]
    if len(result) == 1:
        current_ip = result[0].get("content")
        logger.debug("Current IP in record: '{}'", current_ip)

        ip_address = grabhazip()
        if ip_address is None:
            return

        logger.debug("getting dns record id for {}", config.hostname)
        recordid = get_dns_record_id(
            config,
            zoneid,
            name=config.hostname,
            type_name="A",
        )

        if recordid is None:
            logger.error("Bailing - couldn't get record ID for {}", config.hostname)
            return
        if current_ip != ip_address:
            logger.debug("Updating record, new IP: {}", ip_address)
            update_result = update_zone_record(
                config=config,
                zoneid=zoneid,
                recordid=recordid,
                content=ip_address,
                name=config.hostname,
            )

            if update_result is None:
                return
            if update_result.get("success") is not None:
                logger.info(
                    "Successfully updated - result='{}'",
                    update_result["success"],
                )
            else:
                logger.error(
                    "Failed to update: old='{}' new='{}' result='{}'",
                    current_ip,
                    ip_address,
                    update_result,
                )
        else:
            logger.info("No change required")
    else:
        logger.error("No existing records, stopping.")


CONFIG_FILES = [
    "~/update_dns.conf",
    "/etc/update_dns.conf",
    "/data/update_dns.conf",
    "./update_dns.conf",
    "update_dns.json",
]


def load_config() -> Optional[ConfigFile]:
    """load the config"""

    res = None
    for filename in CONFIG_FILES:
        config_filename = Path(filename).expanduser().resolve()
        if config_filename.exists():
            # token = config_filename.open(encoding='utf-8').read().strip()
            res = ConfigFile.parse_file(config_filename)
            break
        else:
            logger.debug("Couldn't find {}", config_filename)
    if res is not None:
        if os.getenv("DRY_RUN"):
            res.dry_run = True
            logger.info("DRY_RUN is set, not actually updating anything")
        if "--dry-run" in sys.argv:
            res.dry_run = True
            logger.info("DRY_RUN is set, not actually updating anything")
    return res


def main() -> None:
    """main func"""
    config = load_config()

    if config is None:
        logger.error(
            "Couldn't find configuration file, looked in: {}", ",".join(CONFIG_FILES)
        )
        sys.exit(1)
    setup_logging(logger, "--debug" in sys.argv)
    cli(config)


if __name__ == "__main__":
    main()
