import requests
from bs4 import BeautifulSoup


def get_description_and_title_corrections():
    # Studio channel descriptions doc (publicly readable)
    doc_id = '1PQi6y-A4ZYQOepUpe4lldK3gbquUSy3e9NLEGeIex8c'

    # Export to HTML
    gdocs_html_export_url_tpl = "https://docs.google.com/feeds/download/documents/export/Export?id={doc_id}&exportFormat=html"
    response = requests.get(gdocs_html_export_url_tpl.format(doc_id=doc_id))
    doc = BeautifulSoup(response.text, 'html5lib')

    # Get the table
    tables = doc.find_all('table')
    assert len(tables) == 1, 'make sure only one table'
    descr_table = tables[0]


    # Extract only the rows for which there is something in the channel_id
    # (we use presence of channel_id to indicate which descr. we want to edit)
    trs = descr_table.find_all('tr')
    clean_rows = []
    for row in trs[1:]:
        tds = row.find_all('td')
        cols = [td.text.strip() for td in tds]
        channel_id = cols[1]
        if channel_id:
            info = dict(
                channel_title = cols[0],
                channel_id = cols[1],
                new_description = cols[3],
            )
            clean_rows.append(info)

    return clean_rows
