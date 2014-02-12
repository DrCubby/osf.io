"""

"""

import os
import json
import base64
import urllib
import datetime
import StringIO

import requests
from requests_oauthlib import OAuth2Session
from hurry.filesize import size, alternative
from github3 import login

from . import settings as github_settings

GH_URL = 'https://github.com/'
API_URL = 'https://api.github.com/'

# TODO: Move to redis / memcached
github_cache = {}


class GitHub(object):

    def __init__(self, access_token=None, token_type=None):

        self.access_token = access_token
        self.token_type = token_type

        if access_token and token_type:
            self.session = OAuth2Session(
                github_settings.CLIENT_ID,
                token={
                    'access_token': access_token,
                    'token_type': token_type,
                }
            )
            self.gh3 = login(token=access_token)
        else:
            self.session = requests

    @classmethod
    def from_settings(cls, settings):
        if settings:
            return cls(
                access_token=settings.oauth_access_token,
                token_type=settings.oauth_token_type,
            )
        return cls()

    def user(self, user=None):
        """Fetch a user or the authenticated user.

        :param user: Optional GitHub user name; will fetch authenticated
            user if omitted
        :return dict: GitHub API response

        """
        return self.gh3.user(user)

    def repo(self, user, repo):
        """Get a single Github repo's info.

        :param str user: GitHub user name
        :param str repo: GitHub repo name
        :return: Dict of repo information
            See http://developer.github.com/v3/repos/#get

        """
        return self.gh3.repository(user, repo)

    def branches(self, user, repo, branch=None):
        """List a repo's branches or get a single branch.

        :param str user: GitHub user name
        :param str repo: GitHub repo name
        :param str branch: Branch name if getting a single branch
        :return: List of branch dicts
            http://developer.github.com/v3/repos/#list-branches

        """
        return [branch for branch in self.gh3.repository(user, repo).iter_branches()]

    def commits(self, user, repo, path=None, sha=None):
        """Get commits for a repo or file.

        :param str user: GitHub user name
        :param str repo: GitHub repo name
        :param str path: Path to file within repo
        :param str sha: SHA or branch name
        :return list: List of commit dicts from GitHub; see
            http://developer.github.com/v3/repos/commits/

        """
        return [commit for commit in self.gh3.repository(user, repo).iter_commits(sha=sha, path=path)]

    def history(self, user, repo, path, sha=None):
        """Get commit history for a file.

        :param str user: GitHub user name
        :param str repo: GitHub repo name
        :param str path: Path to file within repo
        :param str sha: SHA or branch name
        :return list: List of dicts summarizing commits

        """
        req = self.commits(user, repo, path=path, sha=sha)
        # TODO Fix variables
        if req:
            return [
                {
                    'sha': commit.commit.sha,
                    'name': commit.commit.author['name'],
                    'email': commit.commit.author['email'],
                    'date': commit.commit.author['date'], # Format me?
                }
                for commit in req
            ]

    def tree(self, user, repo, sha, recursive=True):
        """Get file tree for a repo.

        :param str user: GitHub user name
        :param str repo: GitHub repo name
        :param str sha: Branch name or SHA
        :param bool recursive: Walk repo recursively
        :param dict registration_data: Registered commit data
        :returns: tuple: Tuple of commit ID and tree JSON; see
            http://developer.github.com/v3/git/trees/

        """
        # NOTE: GitHub will return the tree recursively as long as the
        # recursive param is included, no matter what its value is
        # Therefore, pass NO params for a NON-recursive tree

        #TODO Test me
        tree = self.gh3.repository(user, repo).tree(sha)
        assert 0, tree
        if recursive:
            return tree.recurse()
        return tree

    def file(self, user, repo, path, ref=None):
        """Get a file within a repo and its contents.

        :returns: A tuple of the form (<filename>, <file_content>, <file_size):

        """
        req = self.contents(user=user, repo=repo, path=path, ref=ref)
        if req:
            return req.name, req.decoded, req.size
        return None, None, None

    def contents(self, user, repo, path='', ref=None):
        """Get the contents of a path within a repo.
        http://developer.github.com/v3/repos/contents/#get-contents

        """
        return self.gh3.repository(user, repo).contents(path, ref)

    def starball(self, user, repo, archive='tar', ref=None):
        """Get link for archive download.

        :param str user: GitHub user name
        :param str repo: GitHub repo name
        :param str archive: Archive format [tar|zip]
        :param str ref: Git reference
        :returns: tuple: Tuple of headers and file location

        """

        return self.gh3.repository(user, repo).archive(archive + 'ball', ref=None)

        url_parts = [
            API_URL, 'repos', user, repo, archive + 'ball'
        ]
        if ref:
            url_parts.append(ref)

        req = self._send(
            os.path.join(*url_parts),
            cache=False,
            output=None,
        )

        if req.status_code == 200:
            return dict(req.headers), req.content
        return None, None

    def set_privacy(self, user, repo, private):
        """Set privacy of GitHub repo.

        :param str user: GitHub user name
        :param str repo: GitHub repo name
        :param bool private: Make repo private; see
            http://developer.github.com/v3/repos/#edit

        """
        req = self._send(
            os.path.join(
                API_URL, 'repos', user, repo
            ),
            method='patch',
            cache=False,
            data=json.dumps({
                'name': repo,
                'private': private,
            })
        )

        return req

    #########
    # Hooks #
    #########

    def hooks(self, user, repo):
        """List webhooks

        :param str user: GitHub user name
        :param str repo: GitHub repo name
        :return list: List of commit dicts from GitHub; see
            http://developer.github.com/v3/repos/hooks/#json-http

        """
        return [hook for hook in self.gh3.repository(user, repo).iter_hooks()]

    def add_hook(self, user, repo, name, config, events=None, active=True):
        """Create a webhook.

        :param str user: GitHub user name
        :param str repo: GitHub repo name
        :return dict: Hook info from GitHub: see see
            http://developer.github.com/v3/repos/hooks/#json-http

        """

        return self.gh3.repository(user, repo).create_hook(name, config, events, active)

    def delete_hook(self, user, repo, _id):
        """Delete a webhook.

        :param str user: GitHub user name
        :param str repo: GitHub repo name
        :return bool: True if successfull False otherwise

        """
        # Note: Must set `output` to `None`; no JSON response from this
        # endpoint
        return self.gh3.repository(user, repo).hook(_id).delete()

    ########
    # CRUD #
    ########

    def upload_file(self, user, repo, path, message, content, sha=None, branch=None, committer=None, author=None):

        data = {
            'message': message,
            'content': base64.b64encode(content),
            'sha': sha,
            'branch': branch,
            'committer': committer,
            'author': author,
        }

        return self._send(
            os.path.join(
                API_URL, 'repos', user, repo, 'contents', path
            ),
            method='put',
            cache=False,
            data=json.dumps(data),
        )

    def delete_file(self, user, repo, path, message, sha, branch=None, committer=None, author=None):

        return self.gh3.repository(user, repo).delete_file(path, message, sha, branch, committer, author)

    ########
    # Auth #
    ########

    def revoke_token(self):

        if self.access_token is None:
            return

        return self._send(
            os.path.join(
                API_URL, 'applications', github_settings.CLIENT_ID,
                'tokens', self.access_token,
            ),
            method='delete',
            cache=False,
            output=None,
            auth=(
                github_settings.CLIENT_ID,
                github_settings.CLIENT_SECRET,
            )
        )


def ref_to_params(branch=None, sha=None):

    params = urllib.urlencode({
        key: value
        for key, value in {
            'branch': branch,
            'sha': sha,
        }.iteritems()
        if value
    })
    if params:
        return '?' + params
    return ''


def _build_github_urls(item, node_url, node_api_url, branch, sha):

    quote_path = urllib.quote_plus(item.path)
    params = ref_to_params(branch, sha)

    if item.type in ['tree', 'dir']:
        return {
            'upload': os.path.join(node_api_url, 'github', 'file', quote_path) + '/' + params,
            'fetch': os.path.join(node_api_url, 'github', 'hgrid', item.path) + '/',
        }
    elif item.type in ['file', 'blob']:
        return {
            'view': os.path.join(node_url, 'github', 'file', quote_path) + '/' + params,
            'download': os.path.join(node_api_url, 'github', 'file', 'download', quote_path) + '/' + params,
            'delete': os.path.join(node_api_url, 'github', 'file', quote_path) + '/' + ref_to_params(branch, item.sha),
        }
    raise ValueError
