"""Google Sheets service tools."""

import json
import logging

from mcp.server.fastmcp import FastMCP

from ..auth import get_sheets_service

logger = logging.getLogger(__name__)


def register_tools(mcp: FastMCP):
    """Register all Sheets tools on the shared MCP server."""

    @mcp.tool()
    def get_spreadsheet_metadata(spreadsheet_id: str) -> str:
        """
        Get metadata about a spreadsheet including all sheet names.

        Args:
            spreadsheet_id: The ID of the spreadsheet.
        """
        service = get_sheets_service()
        spreadsheet = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
        sheets_info = []
        for sheet in spreadsheet.get('sheets', []):
            props = sheet.get('properties', {})
            sheets_info.append({
                "sheetId": props.get('sheetId'),
                "title": props.get('title'),
                "index": props.get('index'),
                "rowCount": props.get('gridProperties', {}).get('rowCount'),
                "columnCount": props.get('gridProperties', {}).get('columnCount')
            })
        return json.dumps({
            "spreadsheetId": spreadsheet.get('spreadsheetId'),
            "title": spreadsheet.get('properties', {}).get('title'),
            "sheets": sheets_info
        }, indent=2)

    @mcp.tool()
    def get_sheet_values(spreadsheet_id: str, range: str) -> str:
        """
        Read values from a spreadsheet range.

        Args:
            spreadsheet_id: The ID of the spreadsheet.
            range: The A1 notation range to read (e.g., 'Sheet1!A1:D10' or 'January!A:Z').
        """
        service = get_sheets_service()
        result = service.spreadsheets().values().get(spreadsheetId=spreadsheet_id, range=range).execute()
        return json.dumps({"range": result.get('range'), "values": result.get('values', [])}, indent=2)

    @mcp.tool()
    def update_sheet_values(spreadsheet_id: str, range: str, values: str) -> str:
        """
        Update values in a spreadsheet range.

        Args:
            spreadsheet_id: The ID of the spreadsheet.
            range: The A1 notation range to update (e.g., 'Sheet1!A1:D10').
            values: JSON array of arrays representing rows and columns.
        """
        service = get_sheets_service()
        parsed_values = json.loads(values)
        result = service.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id, range=range,
            valueInputOption='USER_ENTERED', body={'values': parsed_values}
        ).execute()
        return json.dumps({
            "updatedRange": result.get('updatedRange'),
            "updatedRows": result.get('updatedRows'),
            "updatedColumns": result.get('updatedColumns'),
            "updatedCells": result.get('updatedCells')
        }, indent=2)

    @mcp.tool()
    def append_sheet_rows(spreadsheet_id: str, sheet_name: str, values: str) -> str:
        """
        Append rows to the end of a sheet.

        Args:
            spreadsheet_id: The ID of the spreadsheet.
            sheet_name: The name of the sheet to append to.
            values: JSON array of arrays representing rows to append.
        """
        service = get_sheets_service()
        parsed_values = json.loads(values)
        result = service.spreadsheets().values().append(
            spreadsheetId=spreadsheet_id, range=f"{sheet_name}!A:A",
            valueInputOption='USER_ENTERED', insertDataOption='INSERT_ROWS',
            body={'values': parsed_values}
        ).execute()
        return json.dumps({
            "spreadsheetId": result.get('spreadsheetId'),
            "updatedRange": result.get('updates', {}).get('updatedRange'),
            "updatedRows": result.get('updates', {}).get('updatedRows'),
            "updatedCells": result.get('updates', {}).get('updatedCells')
        }, indent=2)

    @mcp.tool()
    def create_spreadsheet(title: str, sheet_names: str = "Sheet1") -> str:
        """
        Create a new spreadsheet.

        Args:
            title: The title of the new spreadsheet.
            sheet_names: Comma-separated list of sheet names to create (e.g., 'January,February,March'). Default: 'Sheet1'.
        """
        service = get_sheets_service()
        sheets = [{'properties': {'title': name.strip(), 'index': i}} for i, name in enumerate(sheet_names.split(','))]
        result = service.spreadsheets().create(body={'properties': {'title': title}, 'sheets': sheets}).execute()
        return json.dumps({
            "spreadsheetId": result.get('spreadsheetId'),
            "title": result.get('properties', {}).get('title'),
            "url": result.get('spreadsheetUrl'),
            "sheets": [s.get('properties', {}).get('title') for s in result.get('sheets', [])]
        }, indent=2)

    @mcp.tool()
    def add_sheet(spreadsheet_id: str, sheet_name: str) -> str:
        """
        Add a new sheet (tab) to an existing spreadsheet.

        Args:
            spreadsheet_id: The ID of the spreadsheet.
            sheet_name: The name of the new sheet to create.
        """
        service = get_sheets_service()
        result = service.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={'requests': [{'addSheet': {'properties': {'title': sheet_name}}}]}
        ).execute()
        reply = result.get('replies', [{}])[0].get('addSheet', {})
        props = reply.get('properties', {})
        return json.dumps({"sheetId": props.get('sheetId'), "title": props.get('title'), "index": props.get('index')}, indent=2)

    @mcp.tool()
    def duplicate_sheet(spreadsheet_id: str, source_sheet_name: str, new_sheet_name: str) -> str:
        """
        Duplicate an existing sheet within the same spreadsheet.

        Args:
            spreadsheet_id: The ID of the spreadsheet.
            source_sheet_name: The name of the sheet to duplicate.
            new_sheet_name: The name for the new duplicated sheet.
        """
        service = get_sheets_service()
        metadata = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
        source_sheet_id = None
        for sheet in metadata.get('sheets', []):
            if sheet.get('properties', {}).get('title') == source_sheet_name:
                source_sheet_id = sheet.get('properties', {}).get('sheetId')
                break
        if source_sheet_id is None:
            return json.dumps({"error": f"Sheet '{source_sheet_name}' not found"})
        result = service.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={'requests': [{'duplicateSheet': {'sourceSheetId': source_sheet_id, 'newSheetName': new_sheet_name}}]}
        ).execute()
        reply = result.get('replies', [{}])[0].get('duplicateSheet', {})
        props = reply.get('properties', {})
        return json.dumps({"sheetId": props.get('sheetId'), "title": props.get('title'), "index": props.get('index')}, indent=2)

    @mcp.tool()
    def clear_sheet_values(spreadsheet_id: str, range: str) -> str:
        """
        Clear values from a spreadsheet range (keeps formatting).

        Args:
            spreadsheet_id: The ID of the spreadsheet.
            range: The A1 notation range to clear (e.g., 'Sheet1!A2:Z1000').
        """
        service = get_sheets_service()
        result = service.spreadsheets().values().clear(spreadsheetId=spreadsheet_id, range=range).execute()
        return json.dumps({"clearedRange": result.get('clearedRange')}, indent=2)

    @mcp.tool()
    def batch_update_values(spreadsheet_id: str, updates: str) -> str:
        """
        Update multiple ranges in a single request.

        Args:
            spreadsheet_id: The ID of the spreadsheet.
            updates: JSON array of update objects, each with 'range' and 'values'.
        """
        service = get_sheets_service()
        parsed_updates = json.loads(updates)
        data = [{'range': u['range'], 'values': u['values']} for u in parsed_updates]
        result = service.spreadsheets().values().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={'valueInputOption': 'USER_ENTERED', 'data': data}
        ).execute()
        return json.dumps({
            "totalUpdatedRows": result.get('totalUpdatedRows'),
            "totalUpdatedColumns": result.get('totalUpdatedColumns'),
            "totalUpdatedCells": result.get('totalUpdatedCells'),
            "totalUpdatedSheets": result.get('totalUpdatedSheets')
        }, indent=2)
