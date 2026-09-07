"""Real validated runtime and synthetic HTTP requests for write-boundary tests."""

from functools import wraps
import json

from django.test import Client

from gouda.local_delivery import run_validated_local_delivery
from gouda.local_classification_write import WRITE_HOST, WRITE_ORIGIN


BOOTSTRAP = "/api/v1/local/classification-write-capability/"
HEADERS = {"HTTP_HOST": WRITE_HOST, "HTTP_ORIGIN": WRITE_ORIGIN,
           "HTTP_ACCEPT": "application/json"}


def write_runtime(function):
    @wraps(function)
    def wrapped(self, *args, **kwargs):
        def run(delivery):
            response = Client().post(BOOTSTRAP, data="{}", content_type="application/json", **HEADERS)
            self.assertEqual(response.status_code, 200)
            self.capability = response.json()["write_capability"]
            self.delivery = delivery
            return function(self, *args, **kwargs)
        return run_validated_local_delivery(
            bind_host="127.0.0.1", port="8000", enable_classification_writes=True,
            classification_write_origin=WRITE_ORIGIN, server_runner=run,
        )
    return wrapped


def classification_path(movement):
    return f"/api/v1/accounts/{movement.account_id}/movements/{movement.pk}/classification/"


def patch_classification(movement, capability, category, revision):
    return Client().patch(
        classification_path(movement),
        data=json.dumps({"category_id": str(category.pk) if category else None,
                         "expected_revision": revision}),
        content_type="application/json", **HEADERS,
        HTTP_X_GOUDA_CLASSIFICATION_WRITE=capability,
    )
