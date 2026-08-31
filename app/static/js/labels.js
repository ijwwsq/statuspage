// Status dictionaries. Single source of truth for the public page and the admin (and for i18n).

export const COMPONENT_STATUS = {
  operational: 'Operational',
  degraded: 'Degraded',
  partial_outage: 'Partial outage',
  major_outage: 'Major outage',
  maintenance: 'Maintenance',
  unknown: 'No data',
};

export const INCIDENT_STATUS = {
  investigating: 'Investigating',
  identified: 'Identified',
  monitoring: 'Monitoring',
  resolved: 'Resolved',
};

export const IMPACT = {
  none: 'None',
  minor: 'Minor',
  major: 'Major',
  critical: 'Critical',
};
