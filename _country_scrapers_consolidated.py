import json as _json
import os as _os
import re as _re
import shutil as _shutil
import tempfile as _tempfile
import urllib as _urllib
import urllib2 as _urllib2
import zipfile as _zipfile

from bs4 import BeautifulSoup as _BeautifulSoup


class _CountryBase:
    def __init__(self, log_data, country, base_path):
        self.new_ids = []

        self.log_data = log_data
        self.country = country
        self.data_path = _os.path.join(base_path, 'Legislation', country, 'Consolidated')

        if 'Consolidated' not in self.log_data:
            self.log_data['Consolidated'] = {country: []}

        for id_val in self._get_version_ids():
            if id_val not in self.log_data['Consolidated'][country]:
                self.new_ids.append(id_val)

    def update_code(self):
        for id_val in self.new_ids:
            print(id_val)

            self._get_code_version(id_val)
            self._extract_code(id_val)

            self.log_data['Consolidated'][self.country].append(id_val)

    def _get_version_ids(self):
        return list()

    def _get_code_version(self, publication_id):
        pass

    def _extract_code(self, publication_id):
        return None


class UnitedStates(_CountryBase):
    def _get_version_ids(self):
        base_url = 'http://uscode.house.gov/download/annualhistoricalarchives/downloadxhtml.shtml'
        soup = _BeautifulSoup(_urllib2.urlopen(base_url))

        tags = [t for t in soup.find_all('a') if '.zip' in t['href']]

        id_vals = [_re.search('[0-9]+', t['href']).group(0) for t in tags]

        return id_vals

    def _get_code_version(self, publication_id):
        dl_url = 'http://uscode.house.gov/download/annualhistoricalarchives/XHTML/' + publication_id + '.zip'
        zip_path = _os.path.join(_tempfile.gettempdir(), self.country + publication_id + '.zip')

        _urllib.urlretrieve(dl_url, zip_path)

        with _zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(_tempfile.gettempdir())

        _os.remove(zip_path)

    def _extract_code(self, publication_id):
        def section_parser(soup):
            def num_search(tag):
                print(tag)
                label = _re.search(u'^\s*\xa7([0-9]+[-\u2014\u2013a-zA-Z0-9]*)', tag.text).group(1).lower()
                print(label)
                return label

            out = {}

            headers_to_exclude = ['omitted', 'repealed', 'transferred', 'renumbered', 'vacant']

            section_head = soup.find('h3',
                                     class_='section-head',
                                     text=lambda text: text and
                                                       all([excl not in text.lower()
                                                            for excl in headers_to_exclude]) and
                                                       _re.search('^\s*\xa7[^\xa7]', text))

            if section_head:
                next_tag = section_head.find_next_sibling(['h3', 'p'])
                section_number = num_search(section_head)

                out[section_number] = []

                while next_tag:
                    # boolean checks for various cases
                    header_bool = 'class' in next_tag.attrs and 'section-head' in next_tag['class'][0]
                    valid_header_bool = all([excl not in next_tag.text.lower() for excl in headers_to_exclude]) and \
                                        _re.search('^\s*\xa7[^\xa7]', next_tag.text)
                    par_bool = 'class' in next_tag.attrs and 'statutory' in next_tag['class'][0]

                    if header_bool and valid_header_bool:
                        # if header and the header is valid, create a new entry and advance to the next tag
                        section_head = next_tag
                        section_number = num_search(section_head)

                        out[section_number] = []

                        next_tag = next_tag.find_next_sibling(['h3', 'p'])

                    elif header_bool:
                        # if invalid header, skip to the next header
                        next_tag = next_tag.find_next_sibling('h3')

                    elif par_bool:
                        # if valid statutory paragraph, add to the current entry and advance to the next tag
                        out[section_number].append(next_tag.text)
                        next_tag = next_tag.find_next_sibling(['h3', 'p'])

                    else:
                        # otherwise, just advance
                        next_tag = next_tag.find_next_sibling(['h3', 'p'])

            return out

        def get_chapter(ch, chapter_list):
            if ch in chapter_list:
                with open(_os.path.join(self.data_path, ch)) as f:
                    ch_data = _json.loads(f.read())
            else:
                ch_data = {}

            return ch_data

        temp_folder = _os.path.join(_tempfile.gettempdir(), publication_id)
        chapters = [fname for fname in _os.listdir(temp_folder) if _re.search('[0-9]+usc[0-9]+[a-z]?\.htm', fname)]

        current_chapters = _os.listdir(self.data_path)

        for ch_name in chapters:
            with open(_os.path.join(temp_folder, ch_name)) as f:
                chapter_soup = _BeautifulSoup(f.read())
                sections = section_parser(chapter_soup)

            ch_to_write = _re.sub('^[0-9]+usc', '', ch_name)
            ch_to_write = _re.sub('\.htm', '.json', ch_to_write)

            chapter_data = get_chapter(ch_to_write, current_chapters)

            for s in sections:
                if s in chapter_data:
                    chapter_data[s][publication_id] = sections[s]
                else:
                    chapter_data[s] = {publication_id: sections[s]}

            to_write = _os.path.join(self.data_path, ch_to_write)
            with open(to_write, 'w') as f:
                f.write(_json.dumps(chapter_data))

        _shutil.rmtree(temp_folder)
