import asyncio
import os
import pytest

import pymorphy2
import string
from async_timeout import timeout

TEXT_ANALISIS_DELAY = 3


def _clean_word(word):
    word = word.replace('«', '').replace('»', '').replace('…', '')
    # FIXME какие еще знаки пунктуации часто встречаются ?
    word = word.strip(string.punctuation)
    return word


async def split_by_words(morph, text):
    """Учитывает знаки пунктуации, регистр и словоформы, выкидывает предлоги."""
    words = []
    for word in text.split():
        cleaned_word = _clean_word(word)
        normalized_word = morph.parse(cleaned_word)[0].normal_form
        if len(normalized_word) > 2 or normalized_word == 'не':
            words.append(normalized_word)
        await asyncio.sleep(0)

    return words


@pytest.mark.asyncio
async def test_split_by_words():
    # Экземпляры MorphAnalyzer занимают 10-15Мб RAM т.к. загружают в память много данных
    # Старайтесь организовать свой код так, чтоб создавать экземпляр MorphAnalyzer заранее и в единственном числе
    morph = pymorphy2.MorphAnalyzer()

    splitted = await split_by_words(morph, 'Во-первых, он хочет, чтобы')
    assert splitted == ['во-первых', 'хотеть', 'чтобы']

    splitted = await split_by_words(morph, '«Удивительно, но это стало началом!»')
    assert splitted == ['удивительно', 'это', 'стать', 'начало']


def calculate_jaundice_rate(article_words, charged_words):
    """Расчитывает желтушность текста,
    принимает список "заряженных" слов и ищет их внутри article_words."""

    if not article_words:
        return 0.0

    found_charged_words = [
        word for word in article_words if word in set(charged_words)
    ]

    score = len(found_charged_words) / len(article_words) * 100

    return round(score, 2)


def test_calculate_jaundice_rate():
    assert -0.01 < calculate_jaundice_rate([], []) < 0.01
    assert 33.0 < calculate_jaundice_rate(
        ['все', 'аутсайдер', 'побег'],
        ['аутсайдер', 'банкротство']
        ) < 34.0


def fetch_charged_words(directory='charged_list'):
    charged_words = []
    for root, dirs, charged_lists in os.walk(directory):
        for charged_list in charged_lists:
            path_list = f'{root}/{charged_list}'
            with open(path_list) as f:
                words = f.read()
                charged_words.extend(words.split())
    return charged_words


async def check_text_for_jaundicity(text, charged_words):
    morph = pymorphy2.MorphAnalyzer()
    async with timeout(TEXT_ANALISIS_DELAY):
        splitted_text = await split_by_words(morph, text)
    rate = calculate_jaundice_rate(splitted_text, charged_words)
    article_len = len(splitted_text)
    return rate, article_len
