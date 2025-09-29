"""
shisis authentication module.

This module provides the `Shisis` class, which implements authentication
against the Moodle instance ISIS (TU Berlin) using Shibboleth SSO.
"""

import base64
import hashlib
import random
import re
from dataclasses import dataclass
from typing import List, Optional, Protocol

import aiohttp
from bs4 import BeautifulSoup as bs4
from bs4.element import Tag

CONTENT_TYPE = "Content-Type"
X_WWW_FORM_URLENCODED = "application/x-www-form-urlencoded"


class Shisis:
    """
    Client for authenticating against ISIS (TU Berlin) via Shibboleth SSO.

    Attributes:
        session (aiohttp.ClientSession): The HTTP session used for requests.

    Nested Classes:
        Error: Custom exception for Shisis-specific errors.
        Tokens: Dataclass holding public and private tokens.
        IdentityProvider: Dataclass describing an identity provider.
        PublicConfig: Dataclass describing the public configuration.
    """

    session: aiohttp.ClientSession

    def __init__(
        self,
        session: aiohttp.ClientSession,
    ) -> None:
        self.session = session

    class Error(Exception):
        pass

    @dataclass
    class Tokens:
        token: str
        private_token: str

    class IdentityProviderProtocol(Protocol):
        url: Optional[str]

    @dataclass
    class IdentityProvider:
        url: Optional[str] = None

        @classmethod
        def from_dict(cls, **entries):
            instance = cls()
            instance.__dict__.update(entries)
            return instance

    class PublicConfigProtocol(Protocol):
        launchurl: Optional[str]
        httpswwwroot: Optional[str]

    @dataclass
    class PublicConfig:
        launchurl: Optional[str] = None
        httpswwwroot: Optional[str] = None

        @classmethod
        def from_dict(cls, **entries):
            instance = cls()
            instance.__dict__.update(entries)
            return instance

    @staticmethod
    def generate_passport() -> float:
        return random.random() * 1000

    @staticmethod
    def extract_token(token: str, url_moodle: str, passport: float) -> Tokens:
        if token is None or "://token=" not in token:
            raise Shisis.Error("SSO failed. Aborting ...")

        token = token.split("://token=", 1)[1]
        token = base64.b64decode(token).decode("utf-8")
        tokens = token.split(":::")
        if len(tokens) == 2:
            pub = tokens[0]
            priv = tokens[1]
        elif len(tokens) == 3:
            checksum = hashlib.md5(
                (url_moodle + str(passport)).encode("utf-8")
            ).hexdigest()
            if checksum != tokens[0]:
                print(f"passport: {passport}")
                raise Shisis.Error(f"Hash does not match. {checksum}!={tokens[0]}")
            pub = tokens[1]
            priv = tokens[2]
        else:
            raise Shisis.Error(f"Received invalid tokens: {tokens}. Aborting ...")

        return Shisis.Tokens(token=pub, private_token=priv)

    async def __shibboleth_execution_e1s1(self, url: str):
        return await self.session.post(
            url + "/idp/profile/SAML2/Redirect/SSO",
            params={"execution": "e1s1"},
            data={
                "shib_idp_ls_exception.shib_idp_session_ss": "",
                "shib_idp_ls_success.shib_idp_session_ss": "true",
                "shib_idp_ls_value.shib_idp_session_ss": "",
                "shib_idp_ls_exception.shib_idp_persistent_ss": "",
                "shib_idp_ls_success.shib_idp_persistent_ss": "true",
                "shib_idp_ls_value.shib_idp_persistent_ss": "",
                "shib_idp_ls_supported": "true",
                "_eventId_proceed": "",
            },
            headers={CONTENT_TYPE: X_WWW_FORM_URLENCODED},
        )

    async def __shibboleth_execution_e1s2(self, url: str, username: str, password: str):
        # we have to do this hack, since the scheme
        # "moodlemobile" will raise an exception
        # if redirects are handled by aiohttp
        token: Optional[str] = None

        # pylint: disable=unused-argument
        async def on_request_redirect(
            session,
            context,
            params: aiohttp.TraceRequestRedirectParams,
        ):
            nonlocal token
            _location = params.response.headers.get("Location")
            if _location and "://token=" in _location:
                token = _location

        trace_config = aiohttp.TraceConfig()
        trace_config.on_request_redirect.append(on_request_redirect)
        trace_config.freeze()
        self.session.trace_configs.append(trace_config)

        data = {}
        try:
            response = await self.session.post(
                url + "/idp/profile/SAML2/Redirect/SSO",
                params={"execution": "e1s2"},
                data={
                    "j_username": username,
                    "j_password": password,
                    "_eventId_proceed": "",
                },
                headers={CONTENT_TYPE: X_WWW_FORM_URLENCODED},
            )

            soup = bs4(await response.text(), "lxml")

            form = soup.find("form")
            if form is None or not isinstance(form, Tag):
                raise Shisis.Error("No form found in response")

            inputs = soup.find_all("input")
            data = {
                input_.get("name"): input_.get("value")
                for input_ in inputs
                if isinstance(input_, Tag)
            }

            action = form.get("action")
            if action is None:
                raise Shisis.Error("No action found in form")
            await self.session.post(
                action if isinstance(action, str) else action[0],
                data=data,
                headers={CONTENT_TYPE: X_WWW_FORM_URLENCODED},
            )

        except (
            ValueError,
            aiohttp.NonHttpUrlRedirectClientError,
        ) as error:
            # this is the exception raised due to
            # aiohttp not knowing how to handle
            # "moodlemobile" scheme
            if not token:
                raise error
        finally:
            if "j_password" in data.keys():
                raise ValueError("Your Credentials were refused. Please check them.")
            self.session.trace_configs.remove(trace_config)

        if not token:
            raise Shisis.Error("Location was None. Aborting ...")

        return token

    async def authenticate(
        self,
        username: str,
        password: str,
        public_config: "Shisis.PublicConfigProtocol" = PublicConfig(
            launchurl="https://isis.tu-berlin.de/admin/tool/mobile/launch.php",
            httpswwwroot="https://isis.tu-berlin.de",
        ),
        # pylint: disable=line-too-long
        identity_providers: "List[Shisis.IdentityProviderProtocol] | Shisis.IdentityProviderProtocol" = IdentityProvider(
            url="https://isis.tu-berlin.de/auth/shibboleth/index.php"
        ),
    ) -> Tokens:
        """Authenticate a user against ISIS using Shibboleth SSO.

        Args:
            username (str): The Shibboleth username.
            password (str): The Shibboleth password.
            public_config (Shisis.PublicConfigProtocol): Public configuration
                data containing the launch URL and HTTPS root.
            identity_providers (Optional[List[Shisis.IdentityProviderProtocol] | Shisis.IdentityProviderProtocol]):
                Identity provider from which to initiate authentication.

        Returns:
            Shisis.Tokens: A dataclass containing the public token and private token.

        Raises:
            Shisis.Error: If configuration or identity provider data is invalid,
                or if token extraction fails.
            ValueError: If login form submission indicates invalid credentials.
        """

        if public_config.launchurl is None:
            raise Shisis.Error("public_config did not provide launchurl")
        if identity_providers is None:
            raise Shisis.Error("Identityproviders is none")
        identity_provider: Optional[str]
        if isinstance(identity_providers, List):
            if len(identity_providers) == 0:
                raise Shisis.Error("Identityproviders list is empty")
            identity_provider = identity_providers[0].url
        else:
            identity_provider = identity_providers.url
        if identity_provider is None:
            raise Shisis.Error("identityprovider is missing url")

        passport = self.generate_passport()
        await self.session.get(
            public_config.launchurl,
            params={"service": "moodle_mobile_app", "passport": passport},
        )

        response = await self.session.get(identity_provider)
        shib = str(response.history[-1].url)
        match = re.search("(https?://[A-Za-z_0-9.-]+).*", shib)
        if not match:
            raise Shisis.Error("Invalid identity provider")
        shib = match.group(1)

        await self.__shibboleth_execution_e1s1(shib)
        token = await self.__shibboleth_execution_e1s2(shib, username, password)

        httpswwwroot = public_config.httpswwwroot
        if httpswwwroot is None:
            raise Shisis.Error("httpswwwroot is None")
        tokens = self.extract_token(token, httpswwwroot, passport)

        return tokens
