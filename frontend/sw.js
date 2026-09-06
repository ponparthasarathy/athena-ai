/* ==========================================================================
   ATHENA PWA BACKGROUND SERVICE WORKER (YouTube-style Lock Screen Push)
   ========================================================================== */

const CACHE_NAME = 'athena-v1.0';

self.addEventListener('install', (event) => {
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(clients.claim());
});

// Background Push Notification Event (Triggers even when phone is locked or browser is closed)
self.addEventListener('push', (event) => {
  let data = {
    title: '⚠️ ATHENA HEALTH EMERGENCY',
    body: 'Heatwave hazard or physiological anomaly detected.',
    icon: '/athena_flowchart_vector.png',
    badge: '/athena_flowchart_vector.png',
    tag: 'athena-emergency-alert'
  };

  if (event.data) {
    try {
      data = event.data.json();
    } catch (e) {
      data.body = event.data.text();
    }
  }

  const options = {
    body: data.body,
    icon: data.icon || '/athena_flowchart_vector.png',
    badge: data.badge || '/athena_flowchart_vector.png',
    tag: data.tag || 'athena-health-alert',
    vibrate: [300, 100, 300, 100, 300], // Phone vibration pattern for emergency
    requireInteraction: true, // Keep notification on lock screen until acknowledged
    data: {
      url: '/'
    },
    actions: [
      { action: 'check', title: '👁️ View Dashboard' },
      { action: 'dismiss', title: '✖ Dismiss' }
    ]
  };

  event.waitUntil(
    self.registration.showNotification(data.title, options)
  );
});

// Notification Click Event (Opens Web Dashboard when user taps notification on lock screen)
self.addEventListener('notificationclick', (event) => {
  event.notification.close();

  if (event.action === 'dismiss') return;

  event.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true }).then((clientList) => {
      for (let client of clientList) {
        if (client.url && 'focus' in client) {
          return client.focus();
        }
      }
      if (clients.openWindow) {
        return clients.openWindow('/');
      }
    })
  );
});
