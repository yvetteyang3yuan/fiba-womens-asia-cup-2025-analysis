import _bootstrap  # noqa: F401

from src.export_csv import export_tables_to_csv


if __name__ == "__main__":
    results = export_tables_to_csv()

    for result in results:
        table = result["table"]
        path = result["path"]
        row_count = result["row_count"]

        if row_count == 0:
            print(f"{table}：该表暂无数据，已导出表头到 {path.as_posix()}")
        else:
            print(f"{table}：已导出 {row_count} 行到 {path.as_posix()}")
