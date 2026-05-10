"""
ai_workflow.py - سير عمل الذكاء الاصطناعي المتكامل
"""

# import txtai
import yaml
from flask import current_app
from app.services.ai_embeddings import AIEmbeddings
from app.services.ai_integration import AIIntegration
from app.models.ai_models import AICommand
import os

class AIWorkflow:
    """إدارة سير عمل الذكاء الاصطناعي"""
    
    def __init__(self, org_id, user_id):
        self.org_id = org_id
        self.user_id = user_id
        self.embeddings = AIEmbeddings(org_id)
        self.integrator = AIIntegration(org_id, user_id)
        self.workflow = None
        self.initialize_workflow()
    
    def initialize_workflow(self):
        """تهيئة سير العمل"""
        try:
            config_path = os.path.join(
                current_app.root_path,
                '..',
                'config',
                'ai_config.yml'
            )
            with open(config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            
            self.workflow = txtai.Workflow(config.get('workflow', []))
            current_app.logger.info("✅ تم تهيئة سير العمل بنجاح")
            
        except Exception as e:
            current_app.logger.error(f"❌ خطأ في تهيئة سير العمل: {str(e)}")
    
    def process_command_with_workflow(self, command, attachments=None):
        """معالجة أمر باستخدام سير العمل"""
        try:
            # الخطوة 1: تحليل المستندات
            documents = []
            if attachments:
                for attachment in attachments:
                    doc_result = self.workflow.execute(
                        "process_command",
                        {"file": attachment.file_path}
                    )
                    documents.append(doc_result)
            
            # الخطوة 2: فهم الأمر
            command_analysis = self.workflow.execute(
                "process_command",
                {
                    "text": command.command_text,
                    "documents": documents
                }
            )
            
            # الخطوة 3: تنفيذ التكامل مع قاعدة البيانات
            integration_result = self.execute_integration(
                command_analysis,
                documents
            )
            
            # الخطوة 4: فهرسة النتائج
            if integration_result.get('data'):
                for item in integration_result['data']:
                    self.embeddings.index_project_data(item.get('id'))
            
            # الخطوة 5: توليد ملخص
            summary = self.workflow.execute(
                "generate_report",
                {"data": integration_result}
            )
            
            return {
                "analysis": command_analysis,
                "integration": integration_result,
                "summary": summary
            }
            
        except Exception as e:
            current_app.logger.error(f"خطأ في سير العمل: {str(e)}")
            return None
    
    def execute_integration(self, analysis, documents):
        """تنفيذ التكامل بناءً على التحليل"""
        results = []
        
        # تحديد نوع الأمر
        intent = analysis.get('intent', 'general')
        
        if intent == 'project':
            result = self.integrator.process_project_command(
                analysis.get('text', ''),
                analysis,
                documents
            )
            results.append(result)
            
        elif intent == 'user':
            result = self.integrator.process_user_command(
                analysis.get('text', ''),
                analysis,
                documents
            )
            results.append(result)
            
        elif intent == 'task':
            result = self.integrator.process_task_command(
                analysis.get('text', ''),
                analysis,
                documents
            )
            results.append(result)
            
        elif intent == 'report':
            result = self.integrator.generate_report(
                analysis.get('text', ''),
                analysis
            )
            results.append(result)
        
        return {
            "results": results,
            "total_count": sum(r.get('count', 0) for r in results)
        }
    
    def generate_workflow_report(self, report_type, params=None):
        """توليد تقرير باستخدام سير العمل"""
        try:
            # البحث عن البيانات
            search_results = self.embeddings.semantic_search(
                params.get('query', ''),
                params.get('filters'),
                params.get('limit', 100)
            )
            
            # تنفيذ سير عمل التقرير
            report = self.workflow.execute(
                "generate_report",
                {
                    "type": report_type,
                    "data": search_results,
                    "params": params
                }
            )
            
            return report
            
        except Exception as e:
            current_app.logger.error(f"خطأ في توليد التقرير: {str(e)}")
            return None
    
    def get_workflow_status(self, workflow_name):
        """الحصول على حالة سير العمل"""
        try:
            status = self.workflow.status(workflow_name)
            return status
        except:
            return None