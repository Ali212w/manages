// main.js - JavaScript مخصص لنظام إدارة المشاريع

$(document).ready(function() {
    // تهيئة التواريخ
    initializeDatePickers();
    
    // تهيئة المرتبات Select2
    initializeSelect2();
    
    // إدارة الحالة النشطة للقوائم
    setActiveMenu();
    
    // تهيئة التحقق من النماذج
    initializeFormValidation();
    
    // تهيئة WebSocket للتحديثات الحية
    initializeWebSocket();
    
    // إدارة تحميل الملفات
    initializeFileUpload();
    
    // تهيئة الرسوم البيانية
    initializeCharts();
});

// تهيئة منتقي التواريخ
function initializeDatePickers() {
    if ($.fn.datepicker) {
        $('.datepicker').datepicker({
            format: 'yyyy-mm-dd',
            autoclose: true,
            todayHighlight: true,
            rtl: true,
            language: 'ar'
        });
    }
    
    if ($.fn.datetimepicker) {
        $('.datetimepicker').datetimepicker({
            format: 'YYYY-MM-DD HH:mm',
            useCurrent: false,
            rtl: true
        });
    }
}

// تهيئة Select2 للمرتبات
function initializeSelect2() {
    if ($.fn.select2) {
        $('.select2').select2({
            dir: 'rtl',
            width: '100%',
            placeholder: 'اختر...',
            allowClear: true
        });
    }
}

// تحديد العنصر النشط في القائمة
function setActiveMenu() {
    const currentPath = window.location.pathname;
    $('.sidebar-menu a, .navbar-nav .nav-link').each(function() {
        const linkPath = $(this).attr('href');
        if (linkPath && currentPath.includes(linkPath.replace('/dashboard', ''))) {
            $(this).addClass('active');
            $(this).closest('.dropdown').find('.dropdown-toggle').addClass('active');
        }
    });
}

// تهيئة التحقق من النماذج
function initializeFormValidation() {
    $('form.needs-validation').on('submit', function(e) {
        if (!this.checkValidity()) {
            e.preventDefault();
            e.stopPropagation();
        }
        $(this).addClass('was-validated');
    });
    
    // تحقق من تطابق كلمة المرور
    $('input[data-match]').on('keyup', function() {
        const confirmField = $(this);
        const originalField = $('#' + confirmField.data('match'));
        const feedback = confirmField.next('.invalid-feedback');
        
        if (confirmField.val() !== originalField.val()) {
            confirmField.addClass('is-invalid');
            if (feedback.length === 0) {
                confirmField.after('<div class="invalid-feedback">كلمة المرور غير متطابقة</div>');
            }
        } else {
            confirmField.removeClass('is-invalid');
            confirmField.next('.invalid-feedback').remove();
        }
    });
}

// تهيئة WebSocket للتحديثات الحية
function initializeWebSocket() {
    if (typeof io !== 'undefined') {
        const socket = io();
        
        socket.on('connect', function() {
            console.log('تم الاتصال بخادم WebSocket');
        });
        
        socket.on('notification', function(data) {
            showNotification(data.title, data.message, data.type);
        });
        
        socket.on('task_update', function(data) {
            updateTaskStatus(data.taskId, data.status);
        });
        
        socket.on('project_update', function(data) {
            updateProjectProgress(data.projectId, data.progress);
        });
        
        socket.on('disconnect', function() {
            console.log('تم قطع الاتصال بخادم WebSocket');
        });
    }
}

// إظهار الإشعارات
function showNotification(title, message, type = 'info') {
    const toast = $(`
        <div class="toast" role="alert">
            <div class="toast-header bg-${type} text-white">
                <strong class="me-auto">${title}</strong>
                <button type="button" class="btn-close btn-close-white" data-bs-dismiss="toast"></button>
            </div>
            <div class="toast-body">
                ${message}
            </div>
        </div>
    `);
    
    $('.toast-container').append(toast);
    const bsToast = new bootstrap.Toast(toast[0]);
    bsToast.show();
    
    setTimeout(() => {
        toast.remove();
    }, 5000);
}

// تحديث حالة المهمة
function updateTaskStatus(taskId, status) {
    const taskElement = $(`[data-task-id="${taskId}"]`);
    if (taskElement.length) {
        const badge = taskElement.find('.task-status');
        badge.removeClass().addClass(`badge bg-${getStatusColor(status)}`);
        badge.text(status);
        
        // إشعار للمستخدم
        if (taskElement.is(':visible')) {
            showNotification('تحديث المهمة', `تم تحديث حالة المهمة إلى "${status}"`, 'info');
        }
    }
}

// تحديث تقدم المشروع
function updateProjectProgress(projectId, progress) {
    const projectElement = $(`[data-project-id="${projectId}"]`);
    if (projectElement.length) {
        const progressBar = projectElement.find('.progress-bar');
        const progressText = projectElement.find('.progress-text');
        
        progressBar.css('width', `${progress}%`);
        progressText.text(`${progress}%`);
        
        // إشعار للمستخدم
        if (projectElement.is(':visible')) {
            showNotification('تحديث المشروع', `تم تحديث تقدم المشروع إلى ${progress}%`, 'info');
        }
    }
}

// الحصول على لون الحالة
function getStatusColor(status) {
    const colors = {
        'completed': 'success',
        'in_progress': 'warning',
        'pending': 'secondary',
        'active': 'success',
        'inactive': 'danger',
        'planning': 'info',
        'cancelled': 'danger',
        'on_hold': 'warning'
    };
    
    return colors[status] || 'secondary';
}

// إدارة تحميل الملفات
function initializeFileUpload() {
    const uploadArea = $('.file-upload-area');
    
    if (uploadArea.length) {
        uploadArea.on('dragover', function(e) {
            e.preventDefault();
            $(this).addClass('dragover');
        });
        
        uploadArea.on('dragleave', function(e) {
            e.preventDefault();
            $(this).removeClass('dragover');
        });
        
        uploadArea.on('drop', function(e) {
            e.preventDefault();
            $(this).removeClass('dragover');
            
            const files = e.originalEvent.dataTransfer.files;
            handleFileUpload(files);
        });
        
        uploadArea.find('input[type="file"]').on('change', function(e) {
            handleFileUpload(e.target.files);
        });
    }
}

// معالجة تحميل الملفات
function handleFileUpload(files) {
    if (files.length > 0) {
        const formData = new FormData();
        
        for (let i = 0; i < files.length; i++) {
            formData.append('files[]', files[i]);
        }
        
        // عرض مؤشر التحميل
        const uploadArea = $('.file-upload-area');
        const originalContent = uploadArea.html();
        uploadArea.html('<div class="spinner-container"><div class="spinner"></div></div>');
        
        // إرسال الملفات
        $.ajax({
            url: '/api/documents/upload',
            type: 'POST',
            data: formData,
            processData: false,
            contentType: false,
            success: function(response) {
                if (response.success) {
                    showNotification('تم التحميل', 'تم تحميل الملفات بنجاح', 'success');
                    
                    // تحديث قائمة الملفات
                    if (typeof updateFileList === 'function') {
                        updateFileList(response.files);
                    }
                } else {
                    showNotification('خطأ في التحميل', response.error || 'حدث خطأ أثناء التحميل', 'danger');
                }
                
                uploadArea.html(originalContent);
            },
            error: function() {
                showNotification('خطأ في التحميل', 'حدث خطأ في الاتصال بالخادم', 'danger');
                uploadArea.html(originalContent);
            }
        });
    }
}

// تهيئة الرسوم البيانية
function initializeCharts() {
    const chartElements = $('.chart-container');
    
    chartElements.each(function() {
        const container = $(this);
        const chartType = container.data('chart-type');
        const chartData = container.data('chart-data');
        
        if (chartData && typeof Chart !== 'undefined') {
            const ctx = container.find('canvas')[0];
            
            if (ctx) {
                new Chart(ctx.getContext('2d'), {
                    type: chartType,
                    data: chartData,
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        plugins: {
                            legend: {
                                position: 'top',
                                rtl: true
                            }
                        },
                        scales: {
                            x: {
                                ticks: {
                                    font: {
                                        family: 'Cairo'
                                    }
                                }
                            },
                            y: {
                                ticks: {
                                    font: {
                                        family: 'Cairo'
                                    }
                                }
                            }
                        }
                    }
                });
            }
        }
    });
}

// تصدير الجداول إلى Excel
function exportToExcel(tableId, filename) {
    const table = document.getElementById(tableId);
    if (table) {
        const wb = XLSX.utils.table_to_book(table, {sheet: "Sheet1"});
        XLSX.writeFile(wb, `${filename}.xlsx`);
    }
}

// طباعة الصفحة
function printPage() {
    window.print();
}

// نسخ النص إلى الحافظة
function copyToClipboard(text, element) {
    navigator.clipboard.writeText(text).then(() => {
        const originalText = $(element).text();
        $(element).text('تم النسخ!');
        setTimeout(() => {
            $(element).text(originalText);
        }, 2000);
    }).catch(err => {
        console.error('فشل في النسخ: ', err);
    });
}

// تصدير البيانات إلى PDF
function exportToPDF(elementId, filename) {
    const element = document.getElementById(elementId);
    if (element) {
        const opt = {
        margin:       1,
        filename:     `${filename}.pdf`,
        image:        { type: 'jpeg', quality: 0.98 },
        html2canvas:  { scale: 2 },
        jsPDF:        { unit: 'in', format: 'letter', orientation: 'portrait' }
        };
        
        html2pdf().set(opt).from(element).save();
    }
}

// البحث والتصفية في الجداول
function filterTable(tableId, searchId) {
    const searchInput = document.getElementById(searchId);
    const table = document.getElementById(tableId);
    
    if (searchInput && table) {
        searchInput.addEventListener('keyup', function() {
        const filter = this.value.toLowerCase();
        const rows = table.getElementsByTagName('tr');
        
        for (let i = 1; i < rows.length; i++) {
            const row = rows[i];
            let found = false;
            
            const cells = row.getElementsByTagName('td');
            for (let j = 0; j < cells.length; j++) {
            const cell = cells[j];
            if (cell.textContent.toLowerCase().indexOf(filter) > -1) {
                found = true;
                break;
            }
            }
            
            row.style.display = found ? '' : 'none';
        }
        });
    }
}

// تحديث العدادات الحيوية
function updateLiveCounters() {
    $('.live-counter').each(function() {
        const element = $(this);
        const target = parseInt(element.data('target'));
        const current = parseInt(element.text().replace(/,/g, ''));
        
        if (!isNaN(target) && !isNaN(current) && target !== current) {
        const increment = target > current ? 1 : -1;
        const duration = 1000; // مللي ثانية
        const step = Math.abs(target - current) / (duration / 50);
        
        let count = current;
        const timer = setInterval(() => {
            count += increment * step;
            
            if ((increment > 0 && count >= target) || (increment < 0 && count <= target)) {
            count = target;
            clearInterval(timer);
            }
            
            element.text(Math.floor(count).toLocaleString());
        }, 50);
        }
    });
}

// إدارة الجلسة والوقت
function sessionManager() {
    let inactivityTime = 0;
    
    const resetTimer = () => {
        inactivityTime = 0;
    };
    
    // إعادة تعيين المؤقت عند أي نشاط
    $(document).on('mousemove keypress scroll click', resetTimer);
    
    // التحقق من الخمول كل دقيقة
    setInterval(() => {
        inactivityTime++;
        
        // تنبيه بعد 10 دقائق من الخمول
        if (inactivityTime === 10) {
        showNotification('جلسة العمل', 'لقد كنت خاملاً لمدة 10 دقائق', 'warning');
        }
        
        // تسجيل خروج بعد 30 دقيقة
        if (inactivityTime === 30) {
        window.location.href = '/auth/logout';
        }
    }, 60000);
}

// تهيئة إدارة الجلسة عند التحميل
$(document).ready(sessionManager);