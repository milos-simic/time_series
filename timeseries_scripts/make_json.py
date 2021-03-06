"""
Open Power System Data

Timeseries Datapackage

make:json.py : create JSON meta data for the Data Package

"""

import pandas as pd
import json
import yaml
import os
import hashlib

# General metadata

metadata_head = '''
hide: yes

profile: tabular-data-package

name: opsd_time_series

title: Time series

description: Load, wind and solar, prices in hourly resolution

long_description: This data package contains different kinds of timeseries
    data relevant for power system modelling, namely electricity consumption 
    (load) for 37 European countries as well as wind and solar power generation
    and capacities and prices for a growing subset of countries. 
    The timeseries become available at different points in time depending on the
    sources. The
    data has been downloaded from the sources, resampled and merged in
    a large CSV file with hourly resolution. Additionally, the data
    available at a higher resolution (Some renewables in-feed, 15
    minutes) is provided in a separate file. All data processing is
    conducted in python and pandas and has been documented in the
    Jupyter notebooks linked below.

homepage: https://data.open-power-system-data.org/time_series/{version}

documentation:
    https://github.com/Open-Power-System-Data/datapackage_timeseries/blob/{version}/main.ipynb

version: '{version}'
created: '{version}'

last_changes: '{changes}'

keywords:
    - Open Power System Data
    - time series
    - power systems
    - in-feed
    - renewables
    - wind
    - solar
    - power consumption
    - power market

geographical-scope: 38 European countries

temporal-scope:
    start: '{start}'
    end: '{end}'

contributors:
    - web: http://neon-energie.de/en/team/
      name: Jonathan Muehlenpfordt
      email: muehlenpfordt@neon-energie.de
      role: author
      organization: Neon Neue Energieökonomik
'''

source_template = '''
- name: {source}
#  web: {web}
'''

excel_resource = '''
- name: time_series
  title: Time series Excel file
  description: All data in one file
  path: time_series.xlsx
  format: xlsx
  mediatype: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet
  bytes: {bytes}
  hash: {hash}
'''

resource_template = '''
- profile: tabular-data-resource
  name: opsd_time_series_{res_key}
  title: Time series {res_key}utes singleindex
  description: All data that is avaialable in {res_key}utes-resolution in singleindex format
  path: time_series_{res_key}_singleindex.csv
  format: csv
  mediatype: text/csv
  encoding: UTF8
  bytes: {bytes}
  hash: {hash}
  dialect: 
      csvddfVersion: 1.0
      delimiter: ","
      lineTerminator: "\\n" 
      header: true
  alternative_formats:
      - path: time_series_{res_key}_singleindex.csv
        stacking: Singleindex
        format: csv
      - path: time_series.xlsx
        stacking: Multiindex
        format: xlsx
      - path: time_series_{res_key}_multiindex.csv
        stacking: Multiindex
        format: csv
      - path: time_series_{res_key}_stacked.csv
        stacking: Stacked
        format: csv
  schema:
    primaryKey: {utc}
    missingValues: ""
    fields:
      - name: {utc}
        description: Start of timeperiod in Coordinated Universal Time
        type: datetime
        format: fmt:%Y-%m-%dT%H%M%SZ
        opsd-contentfilter: true
      - name: {cet}
        description: Start of timeperiod in Central European (Summer-) Time
        type: datetime
        format: fmt:%Y-%m-%dT%H%M%S%z
      - name: {marker}
        description: marker to indicate which columns are missing data in source data
            and has been interpolated (e.g. DE_transnetbw_solar_generation_actual)
        type: string
'''

field_template = '''
      - name: {region}_{variable}_{attribute}
        description: {description}
        type: number
        unit: {unit}
        source:
            name: {source}
            web: {web}
        opsd-properties: 
            Region: "{region}"
            Variable: {variable}_{attribute}
'''

descriptions_template = '''
entsoe_power_statistics: Total load in {geo} in {unit} as published on ENTSO-E Data Portal/Power Statistics
entsoe_transparency: Total load in {geo} in {unit} as published on ENTSO-E Transparency Platform
generation_actual: Actual {tech} generation in {geo} in {unit}
generation_forecast: Forecasted {tech} generation in {geo} in {unit}
capacity: Electrical capacity of {tech} in {geo} in {unit}
profile: Percentage of {tech} capacity producing in {geo}
day_ahead: Day-ahead spot price for {geo} in {unit}
'''

# Dataset-specific metadata

# For each dataset/outputfile, the metadata has an entry in the
# "resources" list and another in the "schemas" dictionary.
# A "schema" consits of a list of "fields", meaning the columns in the dataset.
# The first 2 fields are the timestamps (UTC and CE(S)T).
# For the other fields, we iterate over the columns
# of the MultiIndex index of the datasets to contruct the corresponding
# metadata.
# The file is constructed from different buildings blocks made up of YAML-strings
# as this makes for  more readable code.


def make_json(data_sets, info_cols, version, changes, headers, areas,
              start_from_user, end_from_user):
    '''
    Create a datapackage.json file that complies with the Frictionless
    data JSON Table Schema from the information in the column-MultiIndex.

    Parameters
    ----------
    data_sets: dict of pandas.DataFrames
        A dict with keys '15min' and '60min' and values the respective
        DataFrames
    info_cols : dict of strings
        Names for non-data columns such as for the index, for additional 
        timestamps or the marker column
    version: str
        Version tag of the Data Package
    changes : str
        Desription of the changes from the last version to this one.
    headers : list
        List of strings indicating the level names of the pandas.MultiIndex
        for the columns of the dataframe.
    start_from_user/end_from_user : datetime.date
        Beginning/end of temporal data coverage

    Returns
    ----------
    None

    '''

    # list of files included in the datapackage in YAML-format
    resource_list = excel_resource.format(
        bytes=os.path.getsize('time_series.xlsx'),
        hash=get_sha_hash('time_series.xlsx'))
    source_list = ''  # list of data sources in YAML-format

    for res_key, df in data_sets.items():
        field_list = ''  # list of columns in a file in YAML-format
        file_name = 'time_series_' + res_key + '_singleindex.csv'
        file_size = os.path.getsize(file_name)
        file_hash = get_sha_hash(file_name)

        # Create the field_list (list of of columns) in a file, starting with
        # the index field
        for col in df.columns:
            if col[0] in info_cols.values():
                continue
            h = {k: v for k, v in zip(headers, col)}
            row = areas['area ID'] == h['region']
            primary_concept = areas.loc[row, 'primary concept'].values[0]
            geo = areas[primary_concept][row].values[0]
            if not primary_concept == 'country':
                geo = geo + ' (' + primary_concept + ')'

            descriptions = yaml.load(
                descriptions_template.format(
                    tech=h['variable'], unit=h['unit'], geo=geo))
            try:
                h['description'] = descriptions[h['attribute']]
            except KeyError:
                h['description'] = descriptions[h['variable']]

            field_list = field_list + field_template.format(**h)
            source_list = source_list + source_template.format(**h)

        # All datasets (15min, 30min, 60min) get an entry in the resource list
        resource_list = (resource_list + resource_template.format(
            res_key=res_key, bytes=file_size, hash=file_hash, **info_cols) +
            field_list)

    # Remove duplicates from sources_list. set() returns unique values from a
    # collection, but it cannot compare dicts. Since source_list is a list of of
    # dicts, this requires first converting it to a tuple, then converting it back to a dict.
    # entry is a dict of structure {'name': source_name}
    source_list = [dict(tupleized) for tupleized in set(
        tuple(entry.items()) for entry in yaml.load(source_list)
        if not entry['name'].startswith('own calculation'))]
    source_list.append({'name': 'BNetzA and netztransparenz.de'})

    # Parse the YAML-Strings and stitch the building blocks together
    metadata = yaml.load(metadata_head.format(
        version=version, changes=changes,
        start=start_from_user, end=end_from_user))
    metadata['sources'] = source_list
    metadata['resources'] = yaml.load(resource_list)

    # write the metadata to disk
    datapackage_json = json.dumps(metadata, indent=4, separators=(',', ': '))
    with open('datapackage.json', 'w') as f:
        f.write(datapackage_json)

    return


def get_sha_hash(path, blocksize=65536):
    sha_hasher = hashlib.sha256()
    with open(path, 'rb') as f:
        buffer = f.read(blocksize)
        while len(buffer) > 0:
            sha_hasher.update(buffer)
            buffer = f.read(blocksize)

        return sha_hasher.hexdigest()
