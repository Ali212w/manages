// documents.js - إدارة المستندات في الوقت الحقيقي

class DocumentManager {
    constructor() {
        this.socket = null;
        this.init();
    }
    
    init() {
        this.initializeWebSocket();
        this.setupEventListeners();
        this.initializeFileUpload();
    }
    
    initializeWebSocket() {
        if (typeof io !== 'undefined') {
            this.socket = io('/documents');
            
            this.socket.on('connect', () => {
                console.log('تم الاتصال بخادم المستندات');
            });
            
            this.socket.on('document_uploaded', (data) => {
                this.handleNewDocument(data);
            });
            
            this.socket.on('document_approved', (data) => {
                this.handleDocumentApproval(data);
            });
            
            this.socket.on('document_updated', (data) => {
                this.handleDocumentUpdate(data);
            });
            
            this.socket.on('disconnect', () => {
                console.log('تم قطع الاتصال بخادم المستندات');
            });
        }
    }
    
    setupEventListeners() {
        // البحث الفوري
        $(document).on('keyup', '.document-search', debounce(this.searchDocuments, 500));
        
        // التصفية الفورية
        $(document).on('change', '.document-filter', this.filterDocuments);
        
        // اختيار متعدد
        $(document).on('change', '.document-select-all', this.selectAllDocuments);
        
        // معاينة سريعة
        $(document).on('click', '.quick-preview', this.quickPreview);
    }
    
    initializeFileUpload() {
        // تهيئة سحب وإفلات الملفات
        if ($('#fileDropzone').length) {
            this.setupDragAndDrop();
        }
    }
    
    setupDragAndDrop() {
        const dropzone = $('#fileDropzone');
        
        dropzone.on('dragover', function(e) {
            e.preventDefault();
            $(this).addClass('dragover');
        });
        
        dropzone.on('dragleave', function(e) {
            e.preventDefault();
            $(this).removeClass('dragover');
        });
        
        dropzone.on('drop', function(e) {
            e.preventDefault();
            $(this).removeClass('dragover');
            
            const files = e.originalEvent.dataTransfer.files;
            if (files.length > 0) {
                this.handleDroppedFiles(files);
            }
        }.bind(this));
    }
    
    handleDroppedFiles(files) {
        // عرض الملفات المنسحبة
        const fileList = $('#droppedFiles');
        fileList.empty();
        
        Array.from(files).forEach(file => {
            const fileItem = this.createFileItem(file);
            fileList.append(fileItem);
        });
        
        // إظهار زر الرفع
        $('#uploadDroppedFiles').show();
    }
    
    createFileItem(file) {
        const fileSize = this.formatFileSize(file.size);
        const fileType = this.getFileType(file.name);
        
        return `
            <div class="file-item">
                <div class="file-icon ${fileType}">
                    <i class="fas fa-${this.getFileIcon(fileType)}"></i>
                </div>
                <div class="file-info">
                    <div class="file-name">${file.name}</div>
                    <div class="file-meta">${fileSize} • ${fileType}</div>
                </div>
                <div class="file-progress">
                    <div class="progress">
                        <div class="progress-bar" style="width: 0%"></div>
                    </div>
                </div>
            </div>
        `;
    }
    
    getFileType(filename) {
        const ext = filename.split('.').pop().toLowerCase();
        
        if (ext === 'pdf') return 'pdf';
        if (['doc', 'docx'].includes(ext)) return 'word';
        if (['xls', 'xlsx', 'csv'].includes(ext)) return 'excel';
        if (['jpg', 'jpeg', 'png', 'gif'].includes(ext)) return 'image';
        return 'other';
    }
    
    getFileIcon(fileType) {
        const icons = {
            'pdf': 'file-pdf',
            'word': 'file-word',
            'excel': 'file-excel',
            'image': 'file-image',
            'other': 'file'
        };
        return icons[fileType] || 'file';
    }
    
    formatFileSize(bytes) {
        if (bytes === 0) return '0 بايت';
        const k = 1024;
        const sizes = ['بايت', 'كيلوبايت', 'ميجابايت', 'جيجابايت'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    }
    
    searchDocuments() {
        const searchTerm = $('.document-search').val();
        
        $.ajax({
            url: '/api/documents/search',
            method: 'GET',
            data: { q: searchTerm },
            success: function(response) {
                if (response.success) {
                    this.updateDocumentList(response.documents);
                }
            }.bind(this)
        });
    }
    
    filterDocuments() {
        const filters = {};
        
        $('.document-filter').each(function() {
            const name = $(this).attr('name');
            const value = $(this).val();
            if (value) {
                filters[name] = value;
            }
        });
        
        $.ajax({
            url: '/api/documents/filter',
            method: 'GET',
            data: filters,
            success: function(response) {
                if (response.success) {
                    this.updateDocumentList(response.documents);
                }
            }.bind(this)
        });
    }
    
    updateDocumentList(documents) {
        const container = $('.documents-list');
        container.empty();
        
        if (documents.length === 0) {
            container.html(`
                <div class="empty-state">
                    <i class="fas fa-folder-open fa-3x"></i>
                    <p>لا توجد مستندات</p>
                </div>
            `);
            return;
        }
        
        documents.forEach(doc => {
            const docElement = this.createDocumentElement(doc);
            container.append(docElement);
        });
    }
    
    createDocumentElement(document) {
        const fileType = this.getFileType(document.filename);
        const uploadDate = new Date(document.uploaded_at).toLocaleDateString('ar-SA');
        const fileSize = this.formatFileSize(document.file_size);
        
        return `
            <div class="document-card" data-id="${document.id}">
                <div class="document-header">
                    <div class="document-icon ${fileType}">
                        <i class="fas fa-${this.getFileIcon(fileType)}"></i>
                    </div>
                    <h5 class="document-title">${document.title}</h5>
                    <div class="document-actions">
                        <button class="btn btn-sm btn-outline-primary quick-preview" 
                                data-id="${document.id}">
                            <i class="fas fa-eye"></i>
                        </button>
                        <a href="/documents/${document.id}/download" 
                           class="btn btn-sm btn-outline-success">
                            <i class="fas fa-download"></i>
                        </a>
                    </div>
                </div>
                <div class="document-body">
                    <div class="document-meta">
                        <span class="badge bg-primary">${document.document_type}</span>
                        <small class="text-muted">${uploadDate}</small>
                        <small class="text-muted">${fileSize}</small>
                    </div>
                    <p class="document-description">${document.description || ''}</p>
                </div>
                <div class="document-footer">
                    <div class="form-check">
                        <input class="form-check-input document-select" 
                               type="checkbox" 
                               value="${document.id}">
                    </div>
                    <div class="document-status">
                        ${this.getStatusBadge(document)}
                    </div>
                </div>
            </div>
        `;
    }
    
    getStatusBadge(document) {
        if (!document.requires_approval) {
            return '<span class="badge bg-secondary">لا يتطلب موافقة</span>';
        }
        
        switch(document.approval_status) {
            case 'approved':
                return '<span class="badge bg-success">موافق عليه</span>';
            case 'rejected':
                return '<span class="badge bg-danger">مرفوض</span>';
            default:
                return '<span class="badge bg-warning">بانتظار الموافقة</span>';
        }
    }
    
    handleNewDocument(data) {
        // إشعار بالمستند الجديد
        if (data.user_id !== CURRENT_USER_ID) {
            showNotification('مستند جديد', 
                `تم رفع مستند جديد: ${data.title}`, 
                'info');
        }
        
        // إضافة المستند الجديد للقائمة
        if ($('.documents-list').length) {
            const docElement = this.createDocumentElement(data);
            $('.documents-list').prepend(docElement);
        }
    }
    
    handleDocumentApproval(data) {
        // تحديث حالة الموافقة
        $(`.document-card[data-id="${data.document_id}"] .document-status`)
            .html(this.getStatusBadge(data));
        
        // إشعار
        showNotification('تحديث الموافقة', 
            `تم ${data.approval_status === 'approved' ? 'الموافقة على' : 'رفض'} المستند`, 
            data.approval_status === 'approved' ? 'success' : 'warning');
    }
    
    handleDocumentUpdate(data) {
        // تحديث معلومات المستند
        // يمكن تحديث العناصر المحددة فقط
        console.log('Document updated:', data);
    }
    
    quickPreview(event) {
        const documentId = $(event.target).closest('.quick-preview').data('id');
        
        $.ajax({
            url: `/api/documents/${documentId}/preview`,
            method: 'GET',
            success: function(response) {
                if (response.success) {
                    this.showPreviewModal(response.document);
                }
            }.bind(this)
        });
    }
    
    showPreviewModal(document) {
        const modalHtml = `
            <div class="modal fade" id="quickPreviewModal" tabindex="-1">
                <div class="modal-dialog modal-lg">
                    <div class="modal-content">
                        <div class="modal-header">
                            <h5 class="modal-title">${document.title}</h5>
                            <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                        </div>
                        <div class="modal-body">
                            <div class="preview-content">
                                ${this.getPreviewContent(document)}
                            </div>
                        </div>
                        <div class="modal-footer">
                            <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">إغلاق</button>
                            <a href="/documents/${document.id}/download" class="btn btn-primary">
                                <i class="fas fa-download me-2"></i>تحميل
                            </a>
                        </div>
                    </div>
                </div>
            </div>
        `;
        
        $('body').append(modalHtml);
        const modal = new bootstrap.Modal(document.getElementById('quickPreviewModal'));
        modal.show();
        
        // تنظيف بعد الإغلاق
        $('#quickPreviewModal').on('hidden.bs.modal', function() {
            $(this).remove();
        });
    }
    
    getPreviewContent(document) {
        const fileType = this.getFileType(document.filename);
        
        switch(fileType) {
            case 'image':
                return `<img src="/documents/${document.id}/download" 
                             alt="${document.title}" 
                             style="max-width: 100%;">`;
            case 'pdf':
                return `
                    <div class="alert alert-info">
                        <i class="fas fa-info-circle me-2"></i>
                        لمعاينة ملف PDF، يرجى تحميله أو استخدام المعاينة الكاملة
                    </div>
                `;
            default:
                return `
                    <div class="text-center py-4">
                        <div class="document-icon ${fileType} large mb-3">
                            <i class="fas fa-${this.getFileIcon(fileType)} fa-3x"></i>
                        </div>
                        <h5>${document.title}</h5>
                        <p class="text-muted">لا يمكن معاينة هذا النوع من الملفات مباشرة</p>
                    </div>
                `;
        }
    }
    
    selectAllDocuments(event) {
        const isChecked = $(event.target).is(':checked');
        $('.document-select').prop('checked', isChecked);
    }
    
    // أدوات مساعدة
    debounce(func, wait) {
        let timeout;
        return function executedFunction(...args) {
            const later = () => {
                clearTimeout(timeout);
                func(...args);
            };
            clearTimeout(timeout);
            timeout = setTimeout(later, wait);
        };
    }
}

// تهيئة مدير المستندات
$(document).ready(() => {
    window.documentManager = new DocumentManager();
});