// notifications.js - إدارة الإشعارات في الوقت الحقيقي

class NotificationManager {
    constructor() {
        this.socket = null;
        this.unreadCount = 0;
        this.init();
    }
    
    init() {
        this.initializeWebSocket();
        this.setupEventListeners();
        this.loadUnreadCount();
    }
    
    initializeWebSocket() {
        if (typeof io !== 'undefined') {
            this.socket = io();
            
            this.socket.on('connect', () => {
                console.log('تم الاتصال بخادم الإشعارات');
            });
            
            this.socket.on('new_notification', (data) => {
                this.handleNewNotification(data);
            });
            
            this.socket.on('notification_read', (data) => {
                this.handleNotificationRead(data);
            });
            
            this.socket.on('disconnect', () => {
                console.log('تم قطع الاتصال بخادم الإشعارات');
            });
        }
    }
    
    setupEventListeners() {
        // تحديث العدادات
        $(document).on('click', '.mark-as-read', (e) => {
            this.markAsRead(e.target.dataset.id);
        });
        
        // تحديث التبويب
        document.addEventListener('visibilitychange', () => {
            if (!document.hidden) {
                this.loadUnreadCount();
            }
        });
    }
    
    loadUnreadCount() {
        $.ajax({
            url: '/api/notifications/unread-count',
            method: 'GET',
            success: (response) => {
                if (response.success) {
                    this.unreadCount = response.count;
                    this.updateBadgeCount();
                }
            }
        });
    }
    
    updateBadgeCount() {
        // تحديث جميع العدادات في الصفحة
        $('.notification-badge').each((_, badge) => {
            const $badge = $(badge);
            if (this.unreadCount > 0) {
                $badge.text(this.unreadCount).show();
            } else {
                $badge.hide();
            }
        });
        
        // تحديث عنوان الصفحة
        this.updatePageTitle();
    }
    
    updatePageTitle() {
        const originalTitle = document.title.replace(/^\(\d+\)\s*/, '');
        
        if (this.unreadCount > 0) {
            document.title = `(${this.unreadCount}) ${originalTitle}`;
        } else {
            document.title = originalTitle;
        }
    }
    
    handleNewNotification(data) {
        this.unreadCount++;
        this.updateBadgeCount();
        
        // عرض الإشعار المنبثق
        this.showToastNotification(data);
        
        // إضافة الصوت إذا كان ممكناً
        this.playNotificationSound();
        
        // تحديث قائمة الإشعارات إذا كانت الصفحة مفتوحة
        if ($('#notificationsList').length) {
            this.addToNotificationsList(data);
        }
    }
    
    handleNotificationRead(data) {
        if (data.user_id === CURRENT_USER_ID) {
            this.unreadCount = Math.max(0, this.unreadCount - 1);
            this.updateBadgeCount();
            
            // تحديث واجهة المستخدم
            $(`[data-notification-id="${data.notification_id}"]`).removeClass('unread');
        }
    }
    
    showToastNotification(data) {
        const toast = $(`
            <div class="toast notification-toast" role="alert" data-delay="5000">
                <div class="toast-header bg-${data.notification_type} text-white">
                    <strong class="me-auto">${data.title}</strong>
                    <small class="text-white">الآن</small>
                    <button type="button" class="btn-close btn-close-white" data-bs-dismiss="toast"></button>
                </div>
                <div class="toast-body">
                    ${data.message}
                    ${data.url ? `<a href="${data.url}" class="btn btn-sm btn-outline-primary mt-2">عرض</a>` : ''}
                </div>
            </div>
        `);
        
        $('.toast-container').append(toast);
        const bsToast = new bootstrap.Toast(toast[0]);
        bsToast.show();
        
        // إزالة التبليغ بعد الإغلاق
        toast.on('hidden.bs.toast', () => {
            toast.remove();
        });
    }
    
    playNotificationSound() {
        if (Notification.permission === 'granted') {
            // يمكن إضافة صوت إشعار هنا
            try {
                const audio = new Audio('/static/sounds/notification.mp3');
                audio.volume = 0.3;
                audio.play();
            } catch (e) {
                console.log('لا يمكن تشغيل صوت الإشعار');
            }
        }
    }
    
    addToNotificationsList(data) {
        const notificationHtml = this.createNotificationHtml(data);
        $('#notificationsList').prepend(notificationHtml);
    }
    
    createNotificationHtml(data) {
        return `
            <div class="notification-item unread" data-notification-id="${data.id}">
                <div class="notification-header">
                    <div class="d-flex align-items-center">
                        <div class="notification-icon ${data.notification_type}">
                            <i class="fas fa-bell"></i>
                        </div>
                        <div>
                            <h6 class="mb-1">${data.title}</h6>
                            <div class="notification-type">
                                <span class="badge bg-${data.notification_type}">
                                    ${data.notification_type}
                                </span>
                            </div>
                        </div>
                    </div>
                </div>
                <div class="notification-body">
                    <p class="notification-message">${data.message}</p>
                </div>
            </div>
        `;
    }
    
    markAsRead(notificationId) {
        $.ajax({
            url: `/api/notifications/${notificationId}/read`,
            method: 'POST',
            success: (response) => {
                if (response.success) {
                    $(`[data-notification-id="${notificationId}"]`).removeClass('unread');
                    this.unreadCount = Math.max(0, this.unreadCount - 1);
                    this.updateBadgeCount();
                }
            }
        });
    }
    
    requestNotificationPermission() {
        if ('Notification' in window) {
            Notification.requestPermission().then(permission => {
                if (permission === 'granted') {
                    this.registerServiceWorker();
                }
            });
        }
    }
    
    registerServiceWorker() {
        if ('serviceWorker' in navigator) {
            navigator.serviceWorker.register('/static/js/notifications-sw.js')
                .then(registration => {
                    console.log('Service Worker registered:', registration);
                })
                .catch(error => {
                    console.log('Service Worker registration failed:', error);
                });
        }
    }
}

// تهيئة مدير الإشعارات عند تحميل الصفحة
$(document).ready(() => {
    window.notificationManager = new NotificationManager();
    
    // طلب الإذن للإشعارات
    if (localStorage.getItem('notification_permission_requested') !== 'true') {
        setTimeout(() => {
            notificationManager.requestNotificationPermission();
            localStorage.setItem('notification_permission_requested', 'true');
        }, 3000);
    }
});