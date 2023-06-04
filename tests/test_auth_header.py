""" testing config file things """

from cloudflare_dyndns import ConfigFile

def test_config_file() -> None:
    """ tests getting an auth header back """

    config = ConfigFile(token="helloworld", hostname="foo", zone="bar", dry_run=False)

    assert config.token == "helloworld"

    print(config.auth_headers())
    assert config.auth_headers() == {
        'Authorization': 'Bearer helloworld',
        'Content-Type': 'application/json',
        }
