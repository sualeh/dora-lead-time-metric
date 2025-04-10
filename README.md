# DORA Lead Time Metric

## Lead Time for Changes

Lead Time for Changes is one of the four key DORA (DevOps Research and Assessment) metrics that measure software delivery performance. It measures the time it takes from when code is committed to when it is successfully running in production. A shorter lead time indicates an organization's ability to respond quickly to customer needs and fix problems rapidly.

Typical lead time ranges:

- Elite performers: Less than one hour
- High performers: Between one day and one week
- Medium performers: Between one week and one month
- Low performers: Between one month and six months

These tools help calculate lead time by tracking pull request timestamps from creation to merge, which is one component of the overall lead time metric.


## Environment Configuration

The application requires several environment variables to be set in a `.env` file:

### GitHub Configuration


### Atlassian Configuration
- `ATLASSIAN_TOKEN`: API token for Atlassian/Jira access
  - Generate from Atlassian Account Settings → Security → API tokens
  - Used for retrieving Jira ticket information

- `JIRA_INSTANCE`: Your Jira instance URL (e.g., `company.atlassian.net`)
  - This is the domain portion of your Jira URL

- `EMAIL`: Your Atlassian account email address
  - Required for Jira API authentication
  - Should match the email associated with your Atlassian account
