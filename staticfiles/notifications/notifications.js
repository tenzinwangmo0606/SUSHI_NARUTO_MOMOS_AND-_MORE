document.addEventListener("DOMContentLoaded", function () {
  const root = document.getElementById("notificationsRoot");
  if (!root) return;

  const toggle = document.getElementById("notifToggle");
  const menu = document.getElementById("notifMenu");
  const list = document.getElementById("notifList");
  const badge = document.getElementById("notifBadge");

  function showMenu(show) {
    menu.classList.toggle("hidden", !show);
  }
  toggle.addEventListener("click", e => {
    showMenu(menu.classList.contains("hidden"));
  });

  function renderNotifications(items) {
    if (!items || !items.length) {
      list.innerHTML = '<div class="text-sm text-gray-500 p-2">No notifications</div>';
      badge.style.display = "none";
      badge.textContent = "0";
      return;
    }
    badge.style.display = "inline-flex";
    badge.textContent = items.filter(i => !i.is_read).length;
    list.innerHTML = items.map(i => {
      const readClass = i.is_read ? "text-gray-500" : "text-gray-800 font-medium";
      const time = new Date(i.created_at).toLocaleString();
      const url = i.url || "#";
      return `<a href="${url}" data-id="${i.id}" class="block p-2 hover:bg-gray-50 ${readClass}"><div class="text-sm">${i.title}</div><div class="text-xs text-gray-500">${i.message}</div><div class="text-xs text-gray-400 mt-1">${time}</div></a>`;
    }).join("");
  }

  // fetch initial list
  fetch("/notifications/list/")
    .then(r => r.json())
    .then(data => {
      renderNotifications(data.notifications);
    }).catch(() => {
      list.innerHTML = '<div class="text-sm text-gray-500 p-2">Unable to load notifications</div>';
    });

  // open websocket
  const proto = (location.protocol === "https:") ? "wss" : "ws";
  const wsUrl = proto + "://" + window.location.host + "/ws/notifications/";
  let sock;
  try {
    sock = new WebSocket(wsUrl);
    sock.onmessage = function (e) {
      try {
        const payload = JSON.parse(e.data);
        // prepend the new notification visually
        const currentNodes = Array.from(list.querySelectorAll("a")).map(a => ({
          id: a.dataset.id,
          html: a.outerHTML
        }));
        const newHtml = `<a href="${payload.url || '#'}" data-id="${payload.id || ''}" class="block p-2 hover:bg-gray-50 text-gray-800 font-medium"><div class="text-sm">${payload.title}</div><div class="text-xs text-gray-500">${payload.message}</div><div class="text-xs text-gray-400 mt-1">${new Date().toLocaleString()}</div></a>`;
        list.innerHTML = newHtml + currentNodes.map(n => n.html).join("");
        // update badge
        const current = parseInt(badge.textContent || "0", 10) || 0;
        badge.style.display = "inline-flex";
        badge.textContent = current + 1;
      } catch (_) { /* ignore parse errors */ }
    };
  } catch (err) { /* WS might be disabled in dev */ }

  // mark-read when clicking an item
  list.addEventListener("click", (e) => {
    const a = e.target.closest("a[data-id]");
    if (!a) return;
    const id = a.dataset.id;
    fetch(`/notifications/mark-read/${id}/`, { method: "POST", headers: { "X-Requested-With": "XMLHttpRequest", "X-CSRFToken": getCookie("csrftoken") } })
      .then(r => r.json())
      .then(data => {
        if (data.unread !== undefined) badge.textContent = data.unread;
        if (data.unread === 0) badge.style.display = "none";
        // allow link navigation after marking
        setTimeout(() => { window.location = a.href; }, 120);
      });
    e.preventDefault();
  });

  // helper to read CSRF cookie
  function getCookie(name) {
    const v = document.cookie.match('(^|;)\\s*' + name + '\\s*=\\s*([^;]+)');
    return v ? v.pop() : '';
  }
});
