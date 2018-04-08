import csv
import re
import requests



# INVENTORY (from the Google Sheet titled "Current Chef Scripts (for cloud-chef fabfile)"
################################################################################
GSHEETS_BASE = 'https://docs.google.com/spreadsheets/d/'
INVENTORY_SHEET_ID = '1vx07agIPaboRHthtGGjJqiLQbXzzM1Mr5gUxxnrexq0'
INVENTORY_SHEET_GID = '0'
INVENTORY_SHEET_URL = GSHEETS_BASE + INVENTORY_SHEET_ID + '/export?format=csv&gid=' + INVENTORY_SHEET_GID
INVENTORY_CSV_PATH = 'inventory/chef_inventory.csv'

# CSV header keys
NICKNAME_KEY = 'Nickname'
CHANNEL_ID_KEY = 'Channel ID'
CHANNEL_NAME_KEY = 'Channel Name'
GITHUB_REPO_URL_KEY = 'Github Repo URL'
POST_SETUP_COMMAND_KEY = 'Post-setup command'
WORKING_DIRECTORY_KEY = 'Change Working Directory'
COMMAND_KEY = 'Run Command'
INVENTORY_FIELDNAMES = [
    NICKNAME_KEY,
    CHANNEL_ID_KEY,
    CHANNEL_NAME_KEY,
    GITHUB_REPO_URL_KEY,
    POST_SETUP_COMMAND_KEY,
    WORKING_DIRECTORY_KEY,
    COMMAND_KEY,
]

# Extra keys
CHEFDIRNAME_KEY = 'chefdirname'



def download_inventory_csv():
    response = requests.get(INVENTORY_SHEET_URL)
    csv_data = response.content.decode('utf-8')
    with open(INVENTORY_CSV_PATH, 'w') as csvfile:
        csvfile.write(csv_data)
        # print('Succesfully saved ' + INVENTORY_CSV_PATH)

def _clean_dict(row):
    """
    Transform empty strings values of dict `row` to None.
    """
    row_cleaned = {}
    for key, val in row.items():
        if val is None or val == '':
            row_cleaned[key] = None
        else:
            row_cleaned[key] = val.strip()
    return row_cleaned


def load_inventory():
    download_inventory_csv()
    chefs_inventory = {}
    with open(INVENTORY_CSV_PATH, 'r') as csvfile:
        reader = csv.DictReader(csvfile, fieldnames=INVENTORY_FIELDNAMES)
        next(reader)  # Skip Headers row
        for row in reader:
            clean_row = _clean_dict(row)
            nickname = clean_row[NICKNAME_KEY]
            if not nickname:
                # print('Skipping inventory row', clean_row)
                continue
            dirname = github_repo_to_chefdir(clean_row[GITHUB_REPO_URL_KEY])
            clean_row[CHEFDIRNAME_KEY] = dirname
            chefs_inventory[nickname] = clean_row

    return chefs_inventory



# TODO(ivan): support git:// URLs
# TODO(ivan): support .git suffix in HTTTPs urls
# TODO(ivan): handle all special cases https://github.com/tj/node-github-url-from-git
GITHUB_REPO_NAME_PAT = re.compile(r'https://github.com/(?P<repo_account>\w*?)/(?P<repo_name>[A-Za-z0-9_-]*)')
def github_repo_to_chefdir(github_url):
    """
    """
    if github_url.endswith('/'):
        github_url = github_url[0:-1]
    match = GITHUB_REPO_NAME_PAT.search(github_url)
    if match:
        return match.groupdict()['repo_name']
    else:
        raise ValueError('chefdir cannot be inferred from github repo name...')
    