import itertools
import json
import os
import re
import requests
from nltk.corpus import stopwords
from nltk.stem.snowball import SnowballStemmer
from tom_lib.structure.corpus import Corpus

import reddit_credentials as creds

from collections import Counter, defaultdict
from requests.auth import HTTPBasicAuth
from cStringIO import StringIO

# Get token
client_auth = HTTPBasicAuth(creds.REDDIT_CLIENT_ID,
                            creds.REDDIT_CLIENT_SECRET)
token_post_data = {
    "grant_type": "password",
    "username": creds.REDDIT_UNAME,
    "password": creds.REDDIT_PW
}
token_headers = {"User-Agent": creds.REDDIT_USER_AGENT}
token_resp = requests.post(
    "https://www.reddit.com/api/v1/access_token",
    auth=client_auth, data=token_post_data, headers=token_headers)

REDDIT_ACCESS_TOKEN = json.loads(token_resp.content).get('access_token', '')

auth_req_headers = {"Authorization": "bearer %s" % REDDIT_ACCESS_TOKEN,
                    "User-Agent": creds.REDDIT_USER_AGENT}
req_headers = {"User-Agent": creds.REDDIT_USER_AGENT}

POST_LIMIT = 100
COMMENT_LIMIT = 100


def get_reddit_response(url, headers={}, params={}):
    resp = requests.get(url, params=params, headers=headers)
    if resp.status_code != 200:
        return
    return json.loads(resp.content)

def get_post_item(post, item_id):
    item = post.get('data', {}).get(item_id)
    return item

def get_post_text(post):
    return get_post_item(post, 'selftext')

def get_post_comments(post, limit=100):
    comments_url = get_post_item(post, 'url')
    comments_data = get_reddit_response('%s.json' % comments_url[:-1],
        params={'sort': 'top', 'limit': COMMENT_LIMIT},
        headers=req_headers)

    cmts = ((comments_data[1] or {}).get('data') or {}).get('children')
    cmt_strings = []

    if not cmts:
        return cmt_strings

    cnt = 0
    while cnt < len(cmts) and cnt < limit:
        cmt_strings.append(cmts[cnt].get('data', {}).get('body', ''))
        cnt += 1

    return filter(None, cmt_strings)

def add_sub_data(subr):
    rposts = (subr.get('data') or {}).get('children')
    if rposts:
        idx = -1
        while (idx + 1) < len(rposts):
            idx += 1
            # Try to skip links
            if not get_post_text(rposts[idx]):
                continue

            comments = get_post_comments(rposts[idx])
            # Create the horrid CSV format that tom_lib wants...
            import pdb; pdb.set_trace()  
            csv = ('text\n%s' % ''.join(comments).encode('utf-8'))
            corp = Corpus(StringIO(csv))
            import pdb; pdb.set_trace()

current_dir = os.path.dirname(os.path.realpath(__file__))
for fname in filter(lambda fname: 'subreddits.txt' in fname, os.listdir(current_dir)):
    with open(fname, 'rb') as subs_file:
        subs_list = subs_file.readlines()

    for sub_name in subs_list:
        sub_name = sub_name.strip()
        sub_data = get_reddit_response(
            'http://www.reddit.com/r/%s.json' % sub_name,
            params={'sort': 'new', 'limit': POST_LIMIT*2},
            headers=req_headers)
    add_sub_data(sub_data)
