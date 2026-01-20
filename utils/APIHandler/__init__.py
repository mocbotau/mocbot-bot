import logging
import os
from requests.exceptions import HTTPError
import requests


class BaseAPIClient:
    """Base API client with common HTTP methods."""

    BASE_URL = None
    API_KEY = None
    LOGGER = logging.getLogger(__name__)

    @staticmethod
    def convert_to_int(data):
        """Recursively convert string values to integers where possible."""
        if isinstance(data, dict):
            for key in data:
                try:
                    temp = int(data[key])
                except (TypeError, ValueError):
                    continue
                else:
                    data[key] = temp
        elif isinstance(data, list):
            for i, item in enumerate(data):
                try:
                    temp = int(item)
                except (TypeError, ValueError):
                    continue
                else:
                    data[i] = temp
        return data

    @classmethod
    def _make_request(self, method: str, route: str, body: object = None):
        """Internal method to make HTTP requests."""
        try:
            url = self.BASE_URL + route
            headers = {"X-API-KEY": self.API_KEY}

            if method in ["POST", "PATCH", "PUT"]:
                req = requests.request(method, url, headers=headers, json=body if body is not None else {}, timeout=10)
            else:
                req = requests.request(method, url, headers=headers, timeout=10)

            req.raise_for_status()
        except requests.exceptions.HTTPError as err:
            status = err.args[0].split(":")[0]
            self.LOGGER.error("[API] Request to %s failed with status %s", route, status)
            raise HTTPError(f"{status}", response=getattr(err, 'response', None)) from err
        else:
            if req.status_code == 204:
                return None
            return self.convert_to_int(req.json())

    @classmethod
    def post(self, route: str, body: object = None):
        """Send a POST request."""
        return self._make_request("POST", route, body)

    @classmethod
    def get(self, route: str):
        """Send a GET request."""
        return self._make_request("GET", route)

    @classmethod
    def patch(self, route: str, body: object = None):
        """Send a PATCH request."""
        return self._make_request("PATCH", route, body)

    @classmethod
    def put(self, route: str, body: object = None):
        """Send a PUT request."""
        return self._make_request("PUT", route, body)

    @classmethod
    def delete(self, route: str):
        """Send a DELETE request."""
        return self._make_request("DELETE", route)


class API(BaseAPIClient):
    """Main API client."""

    BASE_URL = os.environ["API_URL"]
    with open(os.environ["API_KEY"], "r", encoding="utf-8") as f:
        API_KEY = f.read().strip()


class ArchiveAPI(BaseAPIClient):
    """Archive API client."""

    BASE_URL = os.environ["ARCHIVE_API_URL"]
    with open(os.environ["ARCHIVE_API_KEY"], "r", encoding="utf-8") as f:
        API_KEY = f.read().strip()
