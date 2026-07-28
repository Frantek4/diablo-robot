import ipaddress
import json
import uuid
from urllib.parse import urlencode

from tplinkrouterc6u import TplinkRouterProvider

from config.settings import settings

ACCOUNT_PATH = "admin/wireguard?form=account"
CONFIG_PATH = "admin/wireguard?form=config"
CREATE_OPERATION = "insert"
DELETE_OPERATION = "remove"


def _get_router():
    router = TplinkRouterProvider.get_client(settings.TPLINK_ROUTER_HOST, settings.TPLINK_ROUTER_PASSWORD)
    router.authorize()
    return router


def _is_error(result) -> bool:
    if isinstance(result, list):
        result = result[0] if result else {}
    return isinstance(result, dict) and result.get("success") is False


def list_accounts() -> list[dict]:
    router = _get_router()
    try:
        result = router.request(ACCOUNT_PATH, "operation=load")
        if not isinstance(result, list):
            raise RuntimeError(f"Respuesta inesperada al listar cuentas de WireGuard: {result}")
        return result
    finally:
        router.logout()


def get_server_config() -> dict:
    router = _get_router()
    try:
        result = router.request(CONFIG_PATH, "operation=read")
        if not isinstance(result, dict):
            raise RuntimeError(f"Respuesta inesperada al leer la config del servidor WireGuard: {result}")
        return result
    finally:
        router.logout()


def create_account(username: str, client_ip: str) -> dict:
    router = _get_router()
    try:
        new_account = {
            "username": username,
            "client_address": f"{client_ip}/24",
            "allowed_server": f"{client_ip}/32",
            "allowed_client": "10.5.5.0/24",
            "psk_enabled": True,
            "key": f"key-{uuid.uuid4()}",
        }
        payload = urlencode({"operation": CREATE_OPERATION, "new": json.dumps(new_account)})
        result = router.request(ACCOUNT_PATH, payload)
        if _is_error(result) or not isinstance(result, dict) or "client_private_key" not in result:
            raise RuntimeError(f"El router no devolvió las claves esperadas al crear la cuenta: {result}")
        return result
    finally:
        router.logout()


def delete_account(key: str, index: int) -> None:
    router = _get_router()
    try:
        payload = urlencode({"operation": DELETE_OPERATION, "key": key, "index": index})
        result = router.request(ACCOUNT_PATH, payload, ignore_errors=True)
        if _is_error(result):
            raise RuntimeError(f"El router no pudo borrar la cuenta key={key} index={index}: {result}")
    finally:
        router.logout()


def next_free_client_ip(accounts: list[dict], server_config: dict) -> str:
    network = ipaddress.ip_interface(server_config["address"]).network
    used_hosts = set()

    for account in accounts:
        try:
            ip = ipaddress.ip_interface(account["client_address"]).ip
            if ip in network:
                used_hosts.add(ip)
        except (KeyError, ValueError):
            continue

    for host in network.hosts():
        if host != network.network_address + 1 and host not in used_hosts:
            return str(host)

    raise RuntimeError("No quedan IPs libres en el rango de WireGuard.")


def build_client_config(credentials: dict, server_config: dict) -> str:
    lines = [
        "[Interface]",
        f"PrivateKey = {credentials['client_private_key']}",
        f"Address = {credentials['client_address']}",
        f"MTU = {settings.WIREGUARD_MTU}",
    ]
    if settings.WIREGUARD_DNS:
        lines.append(f"DNS = {settings.WIREGUARD_DNS}")

    lines += [
        "",
        "[Peer]",
        f"PublicKey = {server_config['public_key']}",
        f"PresharedKey = {credentials['preshared_key']}",
        f"Endpoint = {settings.WIREGUARD_ENDPOINT_HOST}:{server_config['listen_port']}",
        f"AllowedIPs = {settings.WIREGUARD_ALLOWED_IPS}",
        f"PersistentKeepalive = {server_config.get('persistent_keepalive', 25)}",
    ]
    return "\n".join(lines)
