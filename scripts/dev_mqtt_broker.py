from __future__ import annotations

import asyncio

from amqtt.broker import Broker


CONFIG = {
    "listeners": {
        "default": {
            "type": "tcp",
            "bind": "0.0.0.0:1883",
        }
    },
    "sys_interval": 10,
    "topic-check": {"enabled": False},
    "auth": {"allow-anonymous": True},
}


async def main() -> None:
    broker = Broker(CONFIG)
    await broker.start()
    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())
