import datetime
import os

import requests
from dateutil import relativedelta
from lxml import etree


API_URL = 'https://api.github.com'
GRAPHQL_URL = f'{API_URL}/graphql'
USER_NAME = os.environ['USER_NAME']
ACCESS_TOKEN = os.environ['ACCESS_TOKEN']
BIRTHDAY = os.environ.get('BIRTHDAY', '').strip()
HEADERS = {
    'Accept': 'application/vnd.github+json',
    'Authorization': f'Bearer {ACCESS_TOKEN}',
    'X-GitHub-Api-Version': '2022-11-28',
}
TIMEOUT = (10, 30)
SESSION = requests.Session()


def github_get(path, params=None):
    response = SESSION.get(API_URL + path, headers=HEADERS, params=params, timeout=TIMEOUT)
    response.raise_for_status()
    return response.json()


def github_graphql(query, variables):
    response = SESSION.post(
        GRAPHQL_URL,
        headers=HEADERS,
        json={'query': query, 'variables': variables},
        timeout=TIMEOUT,
    )
    response.raise_for_status()
    payload = response.json()
    if payload.get('errors'):
        raise RuntimeError(payload['errors'])
    return payload['data']


def format_duration(diff):
    """Format a relativedelta as years, months, and days."""
    return '{} {}, {} {}, {} {}'.format(
        diff.years,
        pluralize('year', diff.years),
        diff.months,
        pluralize('month', diff.months),
        diff.days,
        pluralize('day', diff.days),
    )


def account_age(created_at):
    """Return the age of the GitHub account as years, months, and days."""
    created = datetime.datetime.fromisoformat(created_at.replace('Z', '+00:00'))
    now = datetime.datetime.now(datetime.timezone.utc)
    return format_duration(relativedelta.relativedelta(now, created))


def birthday_age(birthday):
    """Return the person's age without exposing the birth date in the repo."""
    born = datetime.date.fromisoformat(birthday)
    today = datetime.datetime.now(datetime.timezone.utc).date()
    return format_duration(relativedelta.relativedelta(today, born))


def pluralize(word, value):
    return word if value == 1 else word + 's'


def public_repositories():
    """Fetch all public repositories owned by the profile."""
    repositories = []
    for page in range(1, 11):
        batch = github_get(
            f'/users/{USER_NAME}/repos',
            {'per_page': 100, 'page': page, 'sort': 'updated'},
        )
        repositories.extend(batch)
        if len(batch) < 100:
            break
    return repositories


def contribution_stats():
    """Return commit and contributed-repository counts for the last year."""
    now = datetime.datetime.now(datetime.timezone.utc)
    start = now - datetime.timedelta(days=365)
    query = '''
    query($login: String!, $from: DateTime!, $to: DateTime!) {
      user(login: $login) {
        contributionsCollection(from: $from, to: $to) {
          totalCommitContributions
          totalRepositoriesWithContributedCommits
        }
      }
    }
    '''
    data = github_graphql(query, {
        'login': USER_NAME,
        'from': start.isoformat(),
        'to': now.isoformat(),
    })
    collection = data['user']['contributionsCollection']
    return {
        'commits': collection['totalCommitContributions'],
        'contributed': collection['totalRepositoriesWithContributedCommits'],
    }


def find_and_replace(root, element_id, new_text):
    element = root.find(f'.//*[@id="{element_id}"]')
    if element is not None:
        element.text = str(new_text)


def set_value(root, element_id, value, dots_id=None, target_length=0):
    value = f'{value:,}' if isinstance(value, int) else str(value)
    find_and_replace(root, element_id, value)
    if dots_id:
        remaining = max(0, target_length - len(value))
        if remaining <= 2:
            dots = {0: '', 1: ' ', 2: '. '}[remaining]
        else:
            dots = ' ' + ('.' * remaining) + ' '
        find_and_replace(root, dots_id, dots)


def set_aligned_value(root, element_id, value, dots_id, dots_length):
    """Update a value while keeping its dot leader at a fixed visual column."""
    value = f'{value:,}' if isinstance(value, int) else str(value)
    find_and_replace(root, element_id, value)
    dots = ' ' + ('.' * max(0, dots_length - 2)) + ' '
    find_and_replace(root, dots_id, dots)


def update_svg(filename, user, repositories, contributions, account_age_data, uptime_data):
    tree = etree.parse(filename)
    root = tree.getroot()
    set_aligned_value(root, 'account_age_data', account_age_data, 'account_age_dots', 11)
    set_aligned_value(root, 'uptime_data', uptime_data, 'uptime_dots', 16)
    set_value(root, 'commit_data', contributions['commits'], 'commit_data_dots', 22)
    set_value(root, 'star_data', sum(repo['stargazers_count'] for repo in repositories), 'star_data_dots', 14)
    set_value(root, 'repo_data', len(repositories), 'repo_data_dots', 6)
    set_value(root, 'contrib_data', contributions['contributed'])
    set_value(root, 'follower_data', user['followers'], 'follower_data_dots', 10)
    tree.write(filename, encoding='utf-8', xml_declaration=True)


if __name__ == '__main__':
    profile = github_get(f'/users/{USER_NAME}')
    repositories = public_repositories()
    contributions = contribution_stats()
    account_age_data = account_age(profile['created_at'])
    uptime_data = birthday_age(BIRTHDAY) if BIRTHDAY else account_age_data
    stats = {
        'account_age': account_age_data,
        'uptime': uptime_data,
        'repos': len(repositories),
        'stars': sum(repo['stargazers_count'] for repo in repositories),
        'commits_1y': contributions['commits'],
        'contributed_repos_1y': contributions['contributed'],
        'followers': profile['followers'],
    }
    update_svg('dark_mode.svg', profile, repositories, contributions, account_age_data, uptime_data)
    update_svg('light_mode.svg', profile, repositories, contributions, account_age_data, uptime_data)
    print('Updated profile stats:', stats)
