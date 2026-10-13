"""Lo que puede pasar al hablar con una red, dicho igual para X y para Instagram.

Cada falla se trata distinto y por eso es una clase propia: confundirlas es lo que hacía Nitter, y
el costo era o quedarse horas sin leer por un corte de red, o seguir pidiendo con una cuenta que la
plataforma ya había marcado. La regla que las ordena: **si la falla no se va a ir sola, no sale un
pedido más** hasta que un humano diga que la arregló. Sólo `Throttled` y `Unreachable` vuelven a
intentar solas.
"""

from datetime import datetime


class AccountFlagged(Exception):
    """La plataforma dijo que nuestra cuenta no puede seguir: sesión muerta, checkpoint, bloqueo,
    suspensión o un challenge. No se reintenta nunca solo: volver a pedir con la cuenta marcada es
    lo que la termina de hundir.

    `session_dead` separa la sesión vencida (cookies que ya no sirven: hay que rehacerlas) del
    resto (checkpoint, bloqueo: se resuelve en la app y las cookies pueden seguir sirviendo). Pedir
    con una sesión vencida es una de las señales más claras de que del otro lado hay un programa,
    así que con ésa ni siquiera `reanudar` deja pedir hasta que la sesión en disco sea otra.
    """

    def __init__(self, reason: str, session_dead: bool = False):
        super().__init__(reason)
        self.reason = reason
        self.session_dead = session_dead


class ClientOutdated(Exception):
    """La plataforma cambió algo que el bot no sabe pedir o leer: un endpoint que ya no existe, un
    queryId que rechaza aun recién buscado, un formato de respuesta nuevo.

    No es culpa de la cuenta, pero tampoco se arregla esperando: el mismo pedido mal armado va a
    rebotar igual dentro de seis horas, y un cliente que manda una y otra vez un pedido que el
    servidor rechaza no se parece a ningún navegador. Frena como `AccountFlagged`, hasta que se
    actualice el código y alguien corra `reanudar`.
    """

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


class Throttled(Exception):
    """La plataforma contestó, pero que no, y es de las que se pasan: un 429, un 5xx, un límite de
    follows. Se espera cada vez más, sin apagar el scaneo. Si dijo cuándo se repone, `resets_at` lo
    trae.
    `stale_query` avisa que el pedido en sí quedó viejo (un queryId rotado) y hay que rearmarlo."""

    def __init__(self, reason: str, resets_at: datetime | None = None, stale_query: bool = False):
        super().__init__(reason)
        self.reason = reason
        self.resets_at = resets_at
        self.stale_query = stale_query


class Unreachable(Exception):
    """El pedido no llegó: DNS, TLS, conexión cortada, timeout del Pi.

    Es lo opuesto de `Throttled`: si la plataforma no vio el pedido, esperar horas no protege a
    nadie y sólo nos deja sin posts. Se sigue al ritmo normal.
    """

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


class TargetMissing(Exception):
    """La cuenta que se quería seguir no está o no se deja seguir. No dice nada de la nuestra."""


def dig(node, *keys):
    """Baja por un JSON ajeno sin romperse si falta un tramo: la forma cambia seguido."""
    for key in keys:
        if not isinstance(node, dict):
            return None
        node = node.get(key)
    return node
