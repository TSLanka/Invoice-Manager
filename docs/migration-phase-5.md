# Migration Notes for Phase 5 OCR Schema Changes

## Overview
Phase 5 introduces OCR (Optical Character Recognition) capabilities to the Invoice Processing Job DocType. This requires database schema changes to store OCR results and extraction metadata.

## Schema Changes

### Invoice Processing Job DocType
The following new fields have been added:

#### OCR Extraction Data Section
- **ocr_raw_text** (Long Text, Read-only)
  - Stores the complete raw text extracted from the invoice via OCR
  - Used for debugging and manual verification
  - Not visible to end users in normal workflow

- **parsed_json** (JSON, Read-only) 
  - Contains structured data extracted from the invoice
  - Includes invoice number, date, totals, supplier information
  - Machine-readable format for integration with ERPNext

- **extraction_version** (Data, Read-only)
  - Tracks which version of the extraction pipeline was used
  - Enables debugging and performance comparison
  - Format: "v1.0.0" or similar semantic versioning

- **extraction_log** (Long Text, Read-only)
  - Detailed processing log for debugging failed extractions
  - Contains error messages, processing steps, and performance metrics
  - Helps identify issues with specific invoice formats

### Child Tables
The existing **Invoice Item** child table will be used to store line items extracted from invoices. No modifications required as it already contains the necessary fields:
- description (Text)
- qty (Float) 
- rate (Currency)
- amount (Currency)

## Database Migration

### Automatic Migration
When the app is updated, Frappe will automatically:
1. Add the new fields to the database schema
2. Set default values (empty/null) for existing records
3. Update the DocType metadata

### Manual Steps Required
None - all changes are handled automatically by Frappe's migration system.

## Backward Compatibility

### Existing Data
- All existing Invoice Processing Job records will remain intact
- New OCR fields will be empty for existing records
- Existing functionality will continue to work unchanged

### API Compatibility
- No breaking changes to existing API endpoints
- New OCR fields are optional and read-only
- Existing integrations will continue to function

## Testing Migration

### Development Environment
```bash
# Update the app
bench get-app --branch feature/phase-5-ocr invoice_manager

# Install/update on site
bench --site [your-site] install-app invoice_manager
# OR if already installed:
bench --site [your-site] migrate

# Verify schema changes
bench --site [your-site] console
```

In the console:
```python
# Check if new fields exist
from frappe import get_meta
meta = get_meta("Invoice Processing Job")
print([f.fieldname for f in meta.fields if 'ocr' in f.fieldname or 'extraction' in f.fieldname])
```

### Production Environment
1. **Backup**: Always create a full backup before migration
2. **Test Site**: Run migration on a copy of production data first
3. **Maintenance Mode**: Enable maintenance mode during migration
4. **Verification**: Test key workflows after migration

```bash
# Backup
bench --site [site] backup --with-files

# Migrate
bench --site [site] migrate

# Verify
bench --site [site] console
```

## Rollback Procedure

If rollback is needed:

### Schema Rollback
```sql
-- Remove new fields (use with extreme caution)
ALTER TABLE `tabInvoice Processing Job` 
  DROP COLUMN `ocr_raw_text`,
  DROP COLUMN `parsed_json`, 
  DROP COLUMN `extraction_version`,
  DROP COLUMN `extraction_log`;
```

### App Rollback
```bash
# Switch to previous app version
bench get-app --branch [previous-branch] invoice_manager
bench --site [site] migrate
```

## Performance Considerations

### Database Impact
- **Storage**: OCR text fields may store large amounts of data
- **Indexing**: No additional indexes required for Phase 5
- **Queries**: New fields are read-only, minimal impact on existing queries

### Recommendations
- Monitor database size after migration
- Consider archival strategy for old OCR data
- Regular cleanup of temporary extraction files

## Security Notes

### Data Protection
- OCR fields contain sensitive invoice data
- Same access controls apply as existing Invoice Processing Job
- No additional permissions required

### Audit Trail
- All OCR field changes are tracked via Frappe's version control
- Extraction logs provide audit trail for processing decisions

## Support

### Common Issues
1. **Migration Timeout**: For large datasets, increase migration timeout
2. **Storage Space**: Ensure adequate disk space for OCR data
3. **Permissions**: Verify user permissions after migration

### Getting Help
- Check extraction logs for processing issues
- Monitor system resources during heavy OCR usage
- Contact support with specific error messages and logs

---

**Version**: 1.0.0  
**Created**: September 13, 2025  
**Last Updated**: September 13, 2025