"""Show what was downloaded and how its columns map onto GigBid fields.

    python -m datapipe.inspect
If a field you need shows MISSING but the file has an equivalent column, add that column name to
the field's list in datapipe/sources.yaml.
"""
from __future__ import annotations

from datapipe.load import RAW, SOURCES, files_for, read_any, resolve_columns


def main():
    print(f"raw data folder: {RAW}\n")
    for key, src in SOURCES.items():
        files = files_for(key)
        print(f"== {key}  ({src['kaggle']})  role: {src['role']}")
        if not files:
            print("   NOT DOWNLOADED\n")
            continue
        for f in files:
            df = read_any(f, 5)
            print(f"   file: {f.relative_to(RAW)}  columns: {list(df.columns)}")
            for field, col in resolve_columns(df, key).items():
                print(f"     {field:16} <- {col or 'MISSING'}")
            if len(df):
                row = df.iloc[0].to_dict()
                print("     first row:", {k: (str(v)[:60]) for k, v in list(row.items())[:8]})
        print(f"   licence recorded: {src['licence']}\n")


if __name__ == "__main__":
    main()
