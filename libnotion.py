from datetime import datetime
import logging as LOGGER
import os
from pprint import pprint

from notion.block import CollectionViewBlock
from notion.client import NotionClient
from notion.collection import CollectionRowBlock



# NOTION TOKEN CREDENTIALS
################################################################################
def get_notion_token_v2():
    """
    Look for token in ENV var `NOTION_TOKEN` and in `../creds/secrets.json` under NOTION_API_TOKEN_V2
    """
    token_v2 = os.environ.get('NOTION_TOKEN')
    if token_v2 is None:
        secrets_path = os.path.join(os.path.dirname(__file__), "..", "creds", "secrets.json")
        if os.path.exists(secrets_path):
            with open(secrets_path) as f:
                SECRETS = json.load(f)
                token_v2 = SECRETS.get("NOTION_API_TOKEN_V2")
    if token_v2 is None:
        raise ValueError('Could not find API token. Set `NOTION_TOKEN` ENV var')
    return token_v2


# NOTION CLIENT
################################################################################
def get_notion_client(token_v2=None, **kwargs):
    if token_v2 is None:
        token_v2 = get_notion_token_v2()
    client = NotionClient(token_v2=token_v2, **kwargs)
    return client



# ISSUE TRACKER
################################################################################
ISSUE_TRACKER_TEMPLATE_CVB_ID = 'd383ec64-1d92-4ab9-b577-18844859f5ad'

def get_by_type_and_title(page, type_, title):
    """
    Find the child block of page of type `type_` and title `title`.
    Raises if it finds multiple matches. Returns None if not found.
    """
    results = []
    for block in page.children:
        if block.type == type_ and block.title == title:
            results.append(block)
    if not results:
        return None
    assert len(results) == 1, 'ERROR: found multiple matches'
    return results[0]


def add_issue_tracker_to_card(card, client=None):
    """
    Add the "Issue Tracker" table to a content source or a studio channel card.
    The input `card` can be either a CollectionRowBlock or its id (str).
    """
    # 0. Make sure we haz client
    if client is None:
        client = get_notion_client(monitor=False)

    # 1. Normalize input
    if isinstance(card, str):
        card = client.get_block(card)
    assert isinstance(card, CollectionRowBlock), 'wrong assumption about card type'

    # 2. Check that card doesn't already have an "Issue Tracker" board
    issue_tracker = get_by_type_and_title(card, 'collection_view', 'Issue Tracker')
    if issue_tracker:
        print('The card', card.title, 'already has an Issue Tracker on it.')
        return

    # 3. Load data from template
    template_cvb = client.get_block(ISSUE_TRACKER_TEMPLATE_CVB_ID)
    template_v = template_cvb.views[0]
    template_col = template_cvb.collection
    title = template_cvb.title
    schema = template_col.get('schema')
    template_v_format = template_v.get('format')
    template_col_format = template_col.get('format')

    # 4. Add the "Issue Tracker" table
    cvb = card.children.add_new(CollectionViewBlock)
    collection_id = client.create_record("collection", parent=cvb, schema=schema)
    collection = client.get_collection(collection_id)
    table_view_id = client.create_record("collection_view", parent=cvb, type='table')
    table_view = client.get_collection_view(table_view_id, collection=collection)
    table_view.set("collection_id", collection.id)
    table_view.set('format', template_v_format)
    collection.set('format', template_col_format)
    cvb.set("collection_id", collection.id)
    cvb.set("view_ids", [table_view.id])
    cvb.title = title

    # 5. Copy over the sample row
    template_row = template_col.get_rows()[0]
    sample_data = template_row.get_all_properties()
    sample_data['created'] = datetime.now()
    row = collection.add_row(**sample_data)


# USER LOOKUP HELPER METHOD
################################################################################
LE_STAFF_DATABASE_ID = 'a0557fb355464113b434cea5769286e9'

def get_github_to_notion_user_lookup_table(client=None):
    """
    Returns a dictionary of github username -> notion user ids to be used as
    part of github <> notion interations (issues and pull requests).
    """
    if client is None:
        client = get_notion_client(monitor=False)
    users_cvpb = client.get_block(LE_STAFF_DATABASE_ID)
    col = users_cvpb.collection
    lookup_table = {}
    for user in col.get_rows():
        notion_person = user.get_property('notion_person')
        if notion_person:
            notion_user_id = notion_person[0].id
        github_username = user.get_property('github_username').strip()
        if github_username and notion_user_id:
            lookup_table[github_username] = notion_user_id
    return lookup_table

# GITHUB_TO_NOTION_USER_LOOKUP_TABLE = get_github_to_notion_user_lookup_table()



# Get channel data
################################################################################
def get_channel_data_by_channel_id(client=None):
    """
    Returns json data for all channels. Use to cache results so will run faster.
    """
    if client is None:
        client = get_notion_client(monitor=False)
    # Suudio Channels All Channels view
    studio_channels_url = 'https://www.notion.so/learningequality/761249f8782c48289780d6693431d900?v=44827975ce5f4b23b5157381fac302c4'
    studio_channles_view = client.get_collection_view(studio_channels_url)
    studio_channels = studio_channles_view.collection.get_rows()
    #
    results = {}
    for studio_channel in studio_channels:
        channel_id = studio_channel.get_property('channel_id')
        if '[' in channel_id and ']' in channel_id:
            channel_id = channel_id.split('[')[1].split(']')[0]
        if channel_id:
            results[channel_id] = studio_channel
    return results
