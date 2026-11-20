# Seed sources

## Nicknames

- Dataset: `common_nickname_csv`, maintained by onyxrev
- Source repository: https://github.com/onyxrev/common_nickname_csv
- CSV: https://github.com/onyxrev/common_nickname_csv/blob/master/nicknames.csv
- License: Public domain, as stated by the source repository.
- Changes: removed leading spaces from CSV headers and data fields on 2026-11-20. This was necessary because the original headers ` name` and ` nickname` included leading spaces; Delta rejects those spaces in column names. Leading spaces after delimiters were also removed from data values.

## Company suffixes

- Dataset: Ambect, `legal-entity-suffixes`
- Source: https://github.com/ambect/legal-entity-suffixes
- CSV: https://raw.githubusercontent.com/ambect/legal-entity-suffixes/main/data/legal-suffixes.csv
- License: CC BY 4.0 (https://creativecommons.org/licenses/by/4.0/)
- Changes: downloaded without modifying the source CSV on 2026-11-19.

The dataset lists legal-form suffixes across jurisdictions. Its `suffix` column contains the primary form; `synonyms` contains alternate spellings separated by semicolons. The data is broader than the synthetic US-focused company suffixes in this project.
