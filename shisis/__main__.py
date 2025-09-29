"""
shisis CLI tool.

This script provides a command-line interface to authenticate against
ISIS (TU Berlin) using Shibboleth credentials. It supports retrieving
authentication tokens or a private token for further API access.
"""

import argparse
import asyncio
import json
import os
from typing import Optional
from urllib.parse import quote

import aiohttp

from shisis import Shisis


async def main():
    class Arguments:
        username: Optional[str]
        password: Optional[str]
        token: bool
        private_token: bool

    parser = argparse.ArgumentParser(
        prog="shisis",
    )
    parser.add_argument(
        "-u",
        "--username",
        dest="username",
        help="Shibboleth username (environment: SHISIS_USER)",
    )
    parser.add_argument(
        "-p",
        "--password",
        dest="password",
        help="Shibboleth password (environment: SHISIS_PASS)",
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "-t",
        "--token",
        dest="token",
        action="store_true",
        help="Only print token",
    )
    group.add_argument(
        "-r",
        "--private-token",
        dest="private_token",
        action="store_true",
        help="Only print private_token",
    )

    args = parser.parse_args(namespace=Arguments())
    username = args.username
    password = args.password

    if username is None:
        username = os.environ.get("SHISIS_USER")
    if password is None:
        password = os.environ.get("SHISIS_PASS")

    if username is None or password is None:
        raise ValueError("Username or password are not defined")

    async with aiohttp.ClientSession() as session:
        shisis = Shisis(session)
        query = "?args=" + quote(
            json.dumps(
                [
                    {
                        "index": 0,
                        "methodname": "tool_mobile_get_public_config",
                        "args": {},
                    }
                ]
            )
        )
        url = "https://isis.tu-berlin.de/lib/ajax/service-nologin.php" + query
        response = await session.get(url)
        data = (await response.json())[0]["data"]
        public_config = Shisis.PublicConfig.from_dict(**data)
        identity_providers = Shisis.IdentityProvider.from_dict(
            **data["identityproviders"][0]
        )
        tokens = await shisis.authenticate(
            username, password, public_config, identity_providers
        )
        if args.token:
            print(tokens.token)
        elif args.private_token:
            print(tokens.private_token)
        else:
            print(json.dumps(tokens.__dict__, indent=2))


def cli():
    asyncio.run(main())


if __name__ == "__main__":
    cli()
