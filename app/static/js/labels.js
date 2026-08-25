// Словари статусов. Один источник правды для витрины и админки (и для i18n при переносе).

export const COMPONENT_STATUS = {
  operational: 'Работает',
  degraded: 'Замедление',
  partial_outage: 'Частичный сбой',
  major_outage: 'Сбой',
  maintenance: 'Обслуживание',
  unknown: 'Нет данных',
};

export const INCIDENT_STATUS = {
  investigating: 'Расследуем',
  identified: 'Причина найдена',
  monitoring: 'Наблюдаем',
  resolved: 'Устранено',
};

export const IMPACT = {
  none: 'Без влияния',
  minor: 'Незначительное',
  major: 'Серьёзное',
  critical: 'Критическое',
};
