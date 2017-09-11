import enchant
import itertools
import json
import os
import re
import reddit_credentials as creds
import requests
import textblob

from cStringIO import StringIO
from nltk.corpus import stopwords
from nltk.stem.snowball import SnowballStemmer
from nltk.tokenize import word_tokenize
from requests.auth import HTTPBasicAuth
from tom_lib.structure.corpus import Corpus


class RedditAPIHelper(object):

    def get_request_headers(self):
        """Just get a simple header for reddit requests
        """
        return {"User-Agent": creds.REDDIT_USER_AGENT}

    def get_auth_request_headers(self):
        """Do specialness to get a reddit access token for *authorized*
        request headers.
        """
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
            auth=client_auth, data=token_post_data,
            headers=token_headers
        )
        reddit_access_token = json.loads(token_resp.content).get('access_token', '')

        return {"Authorization": "bearer %s" % reddit_access_token,
                "User-Agent": creds.REDDIT_USER_AGENT}

    def get_reddit_response(self, url, headers={}, params={}):
        resp = requests.get(url, params=params, headers=headers)
        if resp.status_code != 200:
            return
        return json.loads(resp.content)


class RedditTextAnalyzer(object):

    POST_LIMIT = 100
    COMMENT_LIMIT = 100
    MIN_COMMENTS_BLOB_SIZE = 5000
    STOPWORDS = stopwords.words('english')
    ENGLISH_DICT = enchant.Dict('en_US')

    def __init__(self):
        self.api = RedditAPIHelper()
        self.req_headers = self.api.get_request_headers()

    def get_post_item(self, post, item_id):
        item = post.get('data', {}).get(item_id)
        return item

    def get_post_text(self, post):
        return self.get_post_item(post, 'selftext')

    def get_post_comments(self, post, limit=100):
        comments_url = self.get_post_item(post, 'url')
        comments_data = self.api.get_reddit_response('%s.json' % comments_url[:-1],
            params={'sort': 'top', 'limit': self.COMMENT_LIMIT},
            headers=self.req_headers)

        cmts = ((comments_data[1] or {}).get('data') or {}).get('children')
        cmt_strings = []

        if not cmts:
            return cmt_strings

        cnt = 0
        while cnt < len(cmts) and cnt < limit:
            cmt_strings.append(cmts[cnt].get('data', {}).get('body', ''))
            cnt += 1

        return filter(None, cmt_strings)

    def normalize_text(self, text_str):
        """Prepare a blob of text for analysis by:

           1. Filtering out non-English words. We must do this before tokenization,
              since tokens may not be proper words themselves. We will make perhaps
              unfortunate assumption of spaces as delimiters.
           2. Unifying to lowercase
           3. Intermediate NLTK word tokenization
           4. Removal of stop words, which the rely on tokens in this case.
        """
        text_str = ' '.join(word for word in text_str.split(' ')
                                if word and self.ENGLISH_DICT.check(word))
        text_tokens = word_tokenize(text_str.lower())
        text_tokens = [word.replace("'", "") for word in text_tokens]
        return ' '.join(word for word in text_tokens if word not in self.STOPWORDS)

    def get_sub_comments_sample(self, subr):
        """Obtain a large (>= MIN_COMMENTS_BLOB_SIZE) sample of comments from
        a particular subreddit that has at least POST_LIMIT posts.
        """
        sub_posts = (subr.get('data') or {}).get('children')
        if not sub_posts or len(sub_posts) < self.POST_LIMIT:
            print '**Skipping a subreddit with too few posts.**'
            return None

        combined_comments, idx = '', -1
        while (idx + 1) < len(sub_posts):
            idx += 1
            # Try to skip links
            if not self.get_post_text(sub_posts[idx]):
                continue

            comments = self.get_post_comments(sub_posts[idx])
            combined_comments += self.normalize_text(' '.join(comments))

        if len(combined_comments) < self.MIN_COMMENTS_BLOB_SIZE:
            print '**Skipping a subreddit with too little comments data**'
            return None

        return combined_comments

    def get_sub_vocab_size_ratio(self, subr):
        """We will consider a subreddit's vocabulary size ratio to be the
        ratio of vocabulary size of its Corpus (constructed from its combined
        comments on many posts) to the approximate general size of the
        Corpus.
        """
        sample = self.get_sub_comments_sample(subr)
        if not sample:
            return None

        # Create the CSV format that tom_lib wants
        comments_csv = ('text\n%s' % sample)
        corp = Corpus(StringIO(comments_csv.encode('utf-8')))

        approx_corp_size = float(len(sample.split()))
        approx_vocab_size = float(len(corp.vocabulary))

        return float(approx_vocab_size/approx_corp_size)

    def get_sub_sentiment(self, subr):
        """Create a TextBlob object from combined post/comments blob of a
        given subreddit, and return polarity via the happy library utils.

        Implemenation taken largely from
        http://www.geeksforgeeks.org/twitter-sentiment-analysis-using-python/
        """
        sample = self.get_sub_comments_sample(subr)
        if not sample:
            return None

        blob = textblob.TextBlob(sample)
        return blob.sentiment.polarity


analyzer = RedditTextAnalyzer()

# let's do all teh files because yolololololo
current_dir = os.path.dirname(os.path.realpath(__file__))
for fname in filter(lambda fname: 'subreddits.txt' in fname, os.listdir(current_dir)):
    with open(fname, 'rb') as subs_file:
        subs_list = subs_file.readlines()

    for sub_name in subs_list:
        sub_name = sub_name.strip()
        sub_data = analyzer.api.get_reddit_response(
            'http://www.reddit.com/r/%s.json' % sub_name,
            params={'sort': 'new', 'limit': analyzer.POST_LIMIT},
            headers=analyzer.api.get_request_headers())
        print (
               '%s:\n'
               'Vocabulary size ratio: %s\n'
               'Sentiment: %s\n\n' % (
               sub_name,
               analyzer.get_sub_vocab_size_ratio(sub_data),
               analyzer.get_sub_sentiment(sub_data))
        )
