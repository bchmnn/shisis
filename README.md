# Shisis

[Shisis](http://shisi.urbanup.com/16192641) (**Sh**ibboleth **ISIS**) is a small library to handle authentication for TU-Berlin's Moodle instance "ISIS" via Shibboleth.

## Install

```bash
pip install shisis-async
```

## Usage

### CLI

```bash
$ shisis -h
usage: shisis [-h] [-u USERNAME] [-p PASSWORD] [-t | -r]

options:
  -h, --help            show this help message and exit
  -u, --username USERNAME
                        Shibboleth username (environment: SHISIS_USER)
  -p, --password PASSWORD
                        Shibboleth password (environment: SHISIS_PASS)
  -t, --token           Only print token
  -r, --private-token   Only print private_token
```

### Code

```python
import asyncio

import aiohttp
from shisis import Shisis


async def main():
    async with aiohttp.ClientSession() as session:
        shisis = Shisis(session)
        public_config = Shisis.PublicConfig(
            launchurl="https://isis.tu-berlin.de/admin/tool/mobile/launch.php",
            httpswwwroot="https://isis.tu-berlin.de",
        )
        identity_providers = Shisis.IdentityProvider(
            url="https://isis.tu-berlin.de/auth/shibboleth/index.php"
        )
        tokens = await shisis.authenticate(
            "username", "password", public_config, identity_providers
        )
        print(tokens)


asyncio.run(main())
```

### Code with [poodle_async_full](https://pypi.org/project/poodle-async-full/)

```python
import asyncio
import os

import aiohttp
from poodle_async_full import ApiClient, Configuration, DefaultApi
from shisis import Shisis


async def main():
    configuration = Configuration(host="https://isis.tu-berlin.de")

    async with ApiClient(configuration) as client:
        poodle = DefaultApi(client)
        config = await poodle.tool_mobile_get_public_config()

        async with aiohttp.ClientSession() as shisis_client:
            shisis = Shisis(shisis_client)
            tokens = await shisis.authenticate(
                "username",
                "password",
                config,
                config.identityproviders,
            )
            configuration.api_key["wstoken"] = tokens.token

        site_info = await poodle.core_webservice_get_site_info()
        print(site_info.userid)


asyncio.run(main())
```

