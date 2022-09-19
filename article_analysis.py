import asyncio
import logging
import time
import pytest
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlparse

import aiohttp
from enum import Enum
from async_timeout import timeout

from adapters.inosmi_ru import sanitize
from adapters.exceptions import ArticleNotFound
from text_tools import check_text_for_jaundicity, fetch_charged_words


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


async def process_article(
        session,
        charged_words,
        url,
        jaundicity_results,
        fetch_delay=URL_FETCH_DELAY):

    rate = None
    article_len = None
    try:
        async with timeout(fetch_delay):
            html = await fetch(session, url)

        with log_duration(logger, url):
            sanitized_text = sanitize(html, plaintext=True)
            rate, article_len = await check_text_for_jaundicity(
                sanitized_text,
                charged_words
            )
    except asyncio.exceptions.TimeoutError:
        status = ProcessingStatus.TIMEOUT.name
    except aiohttp.ClientError:
        status = ProcessingStatus.FETCH_ERROR.name
    except ArticleNotFound:
        status = ProcessingStatus.PARSING_ERROR.name
    else:
        status = ProcessingStatus.OK.name
    finally:
        jaundicity_results.append(
            ArticleReport(
                url,
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
        await process_article(
            session,
            charged_words,
            url,
            jaundicity_results
        )
        assert jaundicity_results[0] == ArticleReport(
            url,
            ProcessingStatus.PARSING_ERROR.name
        )

        url = 'https://inosmi.ru/not/exist.html'
        jaundicity_results = []
        await process_article(
            session,
            charged_words,
            url,
            jaundicity_results
        )
        assert jaundicity_results[0] == ArticleReport(
            url,
            ProcessingStatus.FETCH_ERROR.name
        )

        url = 'https://inosmi.ru/politic/20190629/245379332.html'
        jaundicity_results = []
        await process_article(
            session,
            charged_words,
            url,
            jaundicity_results,
            0.1
        )
        assert jaundicity_results[0] == ArticleReport(
            url,
            ProcessingStatus.TIMEOUT.name
        )
