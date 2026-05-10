# app/services/ai_service.py

import json
from datetime import datetime
from flask import current_app
from app.models import db
from app.models.ai_models import AICommand, AICommandAttachment, AIExtraction, AIReport
from app.services.document_processor import DocumentProcessor
from app.services.nlp_processor import NLPProcessor
from app.services.report_generator import ReportGenerator

class AIService:
    """خدمة الذكاء الاصطناعي الرئيسية"""
    
    def __init__(self):
        self.document_processor = DocumentProcessor()
        self.nlp_processor = NLPProcessor()
        self.report_generator = ReportGenerator()
        self.org_id = None
    
    def set_org(self, org_id):
        """تعيين معرف المؤسسة"""
        self.org_id = org_id
    
    def process_command(self, command_id):
        """معالجة أمر ذكاء اصطناعي"""
        command = AICommand.query.get(command_id)
        if not command:
            return {'success': False, 'error': 'الأمر غير موجود'}
        
        try:
            command.status = 'processing'
            command.started_at = datetime.utcnow()
            db.session.commit()
            
            # فهم الأمر
            understanding = self.nlp_processor.understand_command(command.command_text)
            command.command_type = understanding['command_type']
            command.target_type = understanding['target_type']
            command.command_language = understanding['language']
            
            # معالجة المرفقات
            all_text = ""
            attachments_data = []
            
            for attachment in command.attachments:
                result = self.document_processor.process_file(None, attachment.file_path)
                if result['success']:
                    attachment.extracted_text = result['text']
                    attachment.extracted_text_ar = result['text_ar']
                    attachment.extracted_text_en = result['text_en']
                    attachment.language = result['language']
                    attachment.processing_status = 'completed'
                    
                    all_text += result['text'] + "\n\n"
                    attachments_data.append(result)
                    
                else:
                    attachment.processing_status = 'failed'
                    attachment.error_message = result['error']
            
            db.session.commit()
            
            # تنفيذ الأمر حسب النوع
            result = None
            
            if understanding['command_type'] == 'report':
                # توليد تقرير
                result = self.report_generator.generate_report(
                    self.org_id,
                    {
                        'command_text': command.command_text,
                        'target_type': understanding['target_type'],
                        'parameters': understanding['parameters']
                    }
                )
                
                if result['success']:
                    # حفظ التقرير
                    report = AIReport(
                        org_id=self.org_id,
                        created_by=command.user_id,
                        command_id=command.id,
                        report_name=result['title'],
                        report_type=result['report_type'],
                        report_data=result['data'],
                        report_summary=result['summary'],
                        report_insights=result.get('insights'),
                        recommendations=result.get('recommendations'),
                        chart_data=result.get('charts'),
                        created_at=datetime.utcnow()
                    )
                    db.session.add(report)
                    db.session.flush()
                    
                    result['report_id'] = report.id
            
            elif understanding['command_type'] == 'extract':
                # استخراج معلومات
                extracted_info = self.nlp_processor.extract_information(
                    all_text or command.command_text,
                    understanding['target_type']
                )
                
                # إنشاء استخراج
                extraction = AIExtraction(
                    command_id=command.id,
                    extraction_type=understanding['target_type'],
                    extracted_data=extracted_info,
                    confidence=understanding['confidence']
                )
                db.session.add(extraction)
                
                result = {
                    'success': True,
                    'extraction_id': extraction.id,
                    'data': extracted_info,
                    'confidence': understanding['confidence']
                }
            
            else:
                # معالجة عامة
                result = {
                    'success': True,
                    'understanding': understanding,
                    'text': all_text[:500] + '...' if len(all_text) > 500 else all_text
                }
            
            # تحديث الأمر
            command.status = 'completed'
            command.completed_at = datetime.utcnow()
            command.result_summary = result.get('summary', 'تمت المعالجة بنجاح')
            command.result_data = result.get('data')
            command.confidence_score = understanding.get('confidence', 80)
            command.processing_time = (command.completed_at - command.started_at).total_seconds()
            
            db.session.commit()
            
            return {
                'success': True,
                'command_id': command.id,
                'result': result
            }
            
        except Exception as e:
            command.status = 'failed'
            command.processing_notes = str(e)
            db.session.commit()
            
            current_app.logger.error(f"AI Service error: {str(e)}")
            return {'success': False, 'error': str(e)}
    
    def save_extraction(self, extraction_id, user_id, modifications=None):
        """حفظ الاستخراج في قاعدة البيانات"""
        extraction = AIExtraction.query.get(extraction_id)
        if not extraction:
            return {'success': False, 'error': 'الاستخراج غير موجود'}
        
        try:
            data = extraction.extracted_data
            
            if modifications:
                data.update(modifications)
                extraction.user_modifications = modifications
            
            # حفظ حسب النوع
            if extraction.extraction_type == 'project':
                from app.models.project_models import Project, ProjectDates, ProjectBudget
                
                project = Project(
                    org_id=self.org_id,
                    name=data.get('name', 'مشروع جديد'),
                    project_code=data.get('code', f"PRJ-{datetime.now().strftime('%Y%m%d%H%M%S')}"),
                    description=data.get('description')
                )
                
                db.session.add(project)
                db.session.flush()
                
                # إضافة التواريخ
                dates = ProjectDates(project_id=project.id)
                db.session.add(dates)
                
                # إضافة الميزانية
                if data.get('budget'):
                    budget = ProjectBudget(
                        project_id=project.id,
                        original_budget=data['budget'],
                        current_budget=data['budget']
                    )
                    db.session.add(budget)
                
                extraction.linked_project_id = project.id
            
            elif extraction.extraction_type == 'task':
                from app.models.task_models import Task, TaskPlanning
                
                task = Task(
                    task_name=data.get('name', 'مهمة جديدة'),
                    task_code=data.get('code', f"TSK-{datetime.now().strftime('%Y%m%d%H%M%S')}"),
                    description=data.get('description')
                )
                
                db.session.add(task)
                db.session.flush()
                
                if data.get('duration'):
                    planning = TaskPlanning(
                        task_id=task.id,
                        planned_duration=data['duration']
                    )
                    db.session.add(planning)
                
                extraction.linked_task_id = task.id
            
            elif extraction.extraction_type == 'resource':
                from app.models.primavera_models import Resource
                
                resource = Resource(
                    org_id=self.org_id,
                    name=data.get('name', 'مورد جديد'),
                    resource_id=data.get('code', f"RES-{datetime.now().strftime('%Y%m%d%H%M%S')}"),
                    resource_type=data.get('type', 'labor'),
                    unit=data.get('unit', 'hour'),
                    available_quantity=data.get('quantity', 0),
                    cost_per_unit=data.get('cost', 0)
                )
                
                db.session.add(resource)
                extraction.linked_resource_id = resource.id
            
            elif extraction.extraction_type == 'eps':
                from app.models.primavera_models import EPS
                
                eps = EPS(
                    org_id=self.org_id,
                    eps_code=data.get('code', f"EPS-{datetime.now().strftime('%Y%m%d%H%M%S')}"),
                    name=data.get('name', 'EPS جديد'),
                    description=data.get('description')
                )
                
                db.session.add(eps)
                extraction.linked_eps_id = eps.id
            
            # تحديث حالة الاستخراج
            extraction.is_approved = True
            extraction.approved_by = user_id
            extraction.approved_at = datetime.utcnow()
            
            db.session.commit()
            
            return {'success': True, 'id': extraction.linked_project_id or extraction.linked_task_id}
            
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Save extraction error: {str(e)}")
            return {'success': False, 'error': str(e)}