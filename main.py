import aiohttp
import asyncio
import logging
from adapters.inosmi_ru import sanitize
from adapters.exceptions import ArticleNotFound
from text_tools import check_text_for_jaundicity, fetch_charged_words
from anyio import create_task_group
from enum import Enum
from urllib.parse import urlparse
from async_timeout import timeout
from contextlib import contextmanager
import time
from aiohttp import web
from functools import partial
import pymorphy2
from dataclasses import dataclass, asdict
from typing import Optional
import pytest

URL_FETCH_DELAY = 5
logger = logging.getLogger(__name__)


class ProcessingStatus(Enum):
    OK = 'OK'
    FETCH_ERROR = 'FETCH_ERROR'
    PARSING_ERROR = 'PARSING_ERROR'
    TIMEOUT = 'TIMEOUT'

@dataclass
class ArticleReport():
    url: str
    status_code: str
    rate: Optional[float] = None
    length: Optional[int] = None


@contextmanager
def log_duration(logger, url):
    try:
        start = time.monotonic()
        yield
    except asyncio.exceptions.TimeoutError as err:
        duration = round(time.monotonic() - start, 2)
        logger.info(f'Анализ статьи {url} закончен за {duration} сек')
        raise err

    duration = round(time.monotonic() - start, 2)
    logger.info(f'Анализ статьи {url} закончен за {duration} сек')


async def fetch(session, url):
    if urlparse(url).hostname not in ('inosmi.ru', 'dvmn.org'):
        raise ArticleNotFound()

    async with session.get(url) as response:
        response.raise_for_status()
        return await response.text()


async def process_article(session, charged_words, url, title, jaundicity_results, fetch_delay=URL_FETCH_DELAY):
    rate = None
    article_len = None  
    try:
        async with timeout(fetch_delay):
            html = await fetch(session, url)

        with log_duration(logger, url):
            sanitized_text = sanitize(html, plaintext=True)
            rate, article_len = await check_text_for_jaundicity(sanitized_text, charged_words)
    except asyncio.exceptions.TimeoutError:
        status = ProcessingStatus.TIMEOUT.name
    except aiohttp.ClientError:
        status = ProcessingStatus.FETCH_ERROR.name
    except ArticleNotFound:
        status = ProcessingStatus.PARSING_ERROR.name
    else:
        status = ProcessingStatus.OK.name
        
    jaundicity_results.append(
        ArticleReport(
            title,
            status,
            rate,
            article_len
        )
    )

@pytest.mark.asyncio
async def test_process_article():
    charged_words = fetch_charged_words()
    async with aiohttp.ClientSession() as session:
        url = 'https://lenta.ru/brief/2021/08/26/afg_terror/'
        jaundicity_results = []
        await process_article(session, charged_words, url, url, jaundicity_results)
        assert jaundicity_results[0] == ArticleReport(url, ProcessingStatus.PARSING_ERROR.name)

        url = 'https://inosmi.ru/not/exist.html'
        jaundicity_results = []
        await process_article(session, charged_words, url, url, jaundicity_results)
        assert jaundicity_results[0] == ArticleReport(url, ProcessingStatus.FETCH_ERROR.name)

        url = 'https://inosmi.ru/politic/20190629/245379332.html'
        jaundicity_results = []
        await process_article(session, charged_words, url, url, jaundicity_results, 0.1)
        assert jaundicity_results[0] == ArticleReport(url, ProcessingStatus.TIMEOUT.name)


async def handle_request(request, charged_words):
    urls = request.query.get('urls')
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
                tg.start_soon(process_article, session, charged_words, url, url, jaundicity_results)
    response = [asdict(report) for report in jaundicity_results]
    return web.json_response(response)


if __name__ == '__main__':
    logging.basicConfig(
        format='%(levelname)s : %(message)s',
        level=logging.INFO
    )
    app = web.Application()
    charged_words = fetch_charged_words()
    app.add_routes([web.get('/', partial(handle_request, charged_words=charged_words))])
    web.run_app(app)

