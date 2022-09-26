import logging
from dataclasses import asdict
from functools import partial

import aiohttp
from aiohttp import web
from anyio import create_task_group

from article_analysis import process_article
from text_tools import fetch_charged_words


async def handle_request(request, charged_words):
    urls = request.query.get('urls', '').strip()
    if not urls:
        raise web.HTTPBadRequest()
    urls = urls.split(',')
    if len(urls) > 10:
        return web.json_response(
            {"error": "too many urls in request, should be 10 or less"},
            status=400
        )
    jaundicity_results = []
    async with aiohttp.ClientSession() as session:
        async with create_task_group() as tg:
            for url in urls:
                tg.start_soon(
                    process_article,
                    session,
                    charged_words,
                    url,
                    jaundicity_results
                )
    response = [asdict(report) for report in jaundicity_results]
    return web.json_response(response)


if __name__ == '__main__':
    logging.basicConfig(
        format='%(levelname)s : %(message)s',
        level=logging.INFO
    )
    app = web.Application()
    charged_words = fetch_charged_words()
    app.add_routes(
        [web.get('/', partial(
            handle_request,
            charged_words=charged_words
        ))]
    )
    web.run_app(app)
