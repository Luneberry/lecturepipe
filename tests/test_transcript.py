"""transcript 모듈 단위 테스트"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.transcript import parse_video_id


def test_parse_standard_url():
    assert parse_video_id('https://www.youtube.com/watch?v=dQw4w9WgXcQ') == 'dQw4w9WgXcQ'

def test_parse_short_url():
    assert parse_video_id('https://youtu.be/dQw4w9WgXcQ') == 'dQw4w9WgXcQ'

def test_parse_embed_url():
    assert parse_video_id('https://www.youtube.com/embed/dQw4w9WgXcQ') == 'dQw4w9WgXcQ'

def test_parse_shorts_url():
    assert parse_video_id('https://www.youtube.com/shorts/dQw4w9WgXcQ') == 'dQw4w9WgXcQ'

def test_parse_video_id_directly():
    assert parse_video_id('dQw4w9WgXcQ') == 'dQw4w9WgXcQ'

def test_parse_url_with_params():
    assert parse_video_id('https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=120') == 'dQw4w9WgXcQ'

def test_invalid_url():
    try:
        parse_video_id('not-a-url')
        assert False, "Should raise ValueError"
    except ValueError:
        pass


if __name__ == '__main__':
    test_parse_standard_url()
    test_parse_short_url()
    test_parse_embed_url()
    test_parse_shorts_url()
    test_parse_video_id_directly()
    test_parse_url_with_params()
    test_invalid_url()
    print("모든 테스트 통과!")
