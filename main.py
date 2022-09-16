import aiohttp
import asyncio
import os 
import logging
from adapters.inosmi_ru import sanitize
from adapters.exceptions import ArticleNotFound
from text_tools import check_text_for_jaundicity
from anyio import create_task_group
import aiofiles
from enum import Enum
from urllib.parse import urlparse
from async_timeout import timeout
from contextlib import contextmanager
import time


TEST_ARTICLES = ['http://inosmi.ru/economic/20190629/245384784.html', 'https://inosmi.ru/politic/20190629/245379332.html', 'https://dvmn.org/media/filer_public/51/83/51830f54-7ec7-4702-847b-c5790ed3724c/gogol_nikolay_taras_bulba_-_bookscafenet.txt']
URL_FETCH_DELAY = 5

logger = logging.getLogger(__name__)

class ProcessingStatus(Enum):
    OK = 'OK'
    FETCH_ERROR = 'FETCH_ERROR'
    PARSING_ERROR = 'PARSING_ERROR'
    TIMEOUT = 'TIMEOUT'


@contextmanager
def log_duration(logger, url):
    start = time.monotonic()
    yield
    duration = round(time.monotonic() - start, 2)
    logger.info(f'Анализ статьи {url} закончен за {duration} сек')


async def fetch(session, url):
    if urlparse(url).hostname != 'inosmi.ru':
        raise ArticleNotFound()

    async with session.get(url) as response:
        response.raise_for_status()
        return await response.text()


async def fetch_charged_words(directory='charged_list'):
    charged_words = []
    for root, dirs, charged_lists in os.walk(directory):
        for charged_list in charged_lists:
            path_list = f'{root}/{charged_list}'
            async with aiofiles.open(path_list) as f:
                words = await f.read()
                charged_words.extend(words.split())
    return charged_words


async def process_article(session, charged_words, url, title, jaundicity_results):
    rate = None
    article_len = None  
    try:
        async with timeout(URL_FETCH_DELAY):
            html = await fetch(session, url)
    except asyncio.exceptions.TimeoutError:
        status = ProcessingStatus.TIMEOUT.name
    except aiohttp.ClientError:
        status = ProcessingStatus.FETCH_ERROR.name
    except ArticleNotFound:
        status = ProcessingStatus.PARSING_ERROR.name
    else:
        with log_duration(logger, url):
            sanitized_text = sanitize(html, plaintext=True)
            rate, article_len = check_text_for_jaundicity(sanitized_text, charged_words)
        status = ProcessingStatus.OK.name
    jaundicity_results.append(
        {
            'Статус': status,
            'URL:': title,
            'Рейтинг:': rate,
            'Слов в статье:': article_len
        }
    )


async def main():
    logging.basicConfig(
        format='%(levelname)s : %(message)s',
        level=logging.INFO
    )
    jaundicity_results = []
    charged_words = await fetch_charged_words()
    async with aiohttp.ClientSession() as session:
        async with create_task_group() as tg:
            for url in TEST_ARTICLES:
                tg.start_soon(process_article, session, charged_words, url, url, jaundicity_results)
    for result in jaundicity_results:
        print(result)


asyncio.run(main())
