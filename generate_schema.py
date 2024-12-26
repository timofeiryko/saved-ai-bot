from tortoise import Tortoise
import asyncio

async def init():
    await Tortoise.init(
        db_url='sqlite://db.sqlite3',
        modules={'models': ['models']}
    )
    await Tortoise.generate_schemas()

async def shutdown():
    await Tortoise.close_connections()

async def main():
    await init()
    await shutdown()

if __name__ == '__main__':
    asyncio.run(main())

