"""
ai_embeddings.py - خدمات المتجهات والبحث الدلالي
"""

# import txtai
import yaml
from flask import current_app
from app.models import db
from app.models import Project
from app.models.task_models import Task
from app.models.core_models import User
import os

class AIEmbeddings:
    """إدارة المتجهات والبحث الدلالي"""
    
    def __init__(self, org_id):
        self.org_id = org_id
        self.app = None
        self.initialize_embeddings()
    
    def initialize_embeddings(self):
        """تهيئة نظام التضمين"""
        try:
            # تحميل التكوين
            config_path = os.path.join(
                current_app.root_path, 
                '..', 
                'config', 
                'ai_config.yml'
            )
            with open(config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            
            # إنشاء تطبيق txtai
            self.app = txtai.Application(config)
            current_app.logger.info("✅ تم تهيئة نظام التضمين بنجاح")
            
        except Exception as e:
            current_app.logger.error(f"❌ خطأ في تهيئة التضمين: {str(e)}")
    
    def index_project_data(self, project_id):
        """فهرسة بيانات مشروع في نظام البحث"""
        try:
            project = Project.query.get(project_id)
            if not project or project.org_id != self.org_id:
                return False
            
            # إنشاء نص للفهرسة
            text = f"""
            مشروع: {project.name}
            الكود: {project.project_code}
            الوصف: {project.description or ''}
            الموقع: {project.site_name or ''}
            الحالة: {project.status}
            التقدم: {project.progress_percentage}%
            التكلفة المخططة: {project.total_planned_cost}
            التكلفة الفعلية: {project.total_actual_cost}
            """
            
            # إضافة الأنشطة
            activities = project.activities.all()
            for act in activities[:10]:  # حد أقصى 10 أنشطة
                text += f"""
                نشاط: {act.activity_name}
                حالة النشاط: {act.status}
                تقدم النشاط: {act.progress_percentage}%
                """
            
            # فهرسة في txtai
            self.app.add_document(
                f"project_{project.id}",
                text,
                tags=["project", project.status],
                metadata={
                    "id": project.id,
                    "type": "project",
                    "org_id": self.org_id,
                    "created_at": str(project.created_at)
                }
            )
            
            return True
            
        except Exception as e:
            current_app.logger.error(f"خطأ في فهرسة المشروع: {str(e)}")
            return False
    
    def index_all_organization_data(self):
        """فهرسة جميع بيانات المؤسسة"""
        try:
            # فهرسة المشاريع
            projects = Project.query.filter_by(org_id=self.org_id).all()
            for project in projects:
                self.index_project_data(project.id)
            
            # فهرسة المهام
            tasks = Task.query.join(Project).filter(
                Project.org_id == self.org_id
            ).limit(500).all()
            
            for task in tasks:
                text = f"""
                مهمة: {task.task_name}
                الكود: {task.task_code}
                الوصف: {task.description or ''}
                الحالة: {task.status}
                التقدم: {task.progress_percentage}%
                المشروع: {task.project.name if task.project else ''}
                """
                
                self.app.add_document(
                    f"task_{task.id}",
                    text,
                    tags=["task", task.status],
                    metadata={
                        "id": task.id,
                        "type": "task",
                        "project_id": task.project_id,
                        "org_id": self.org_id
                    }
                )
            
            # حفظ الفهارس
            self.app.save(f"../data/embeddings/org_{self.org_id}")
            
            return {
                "projects_indexed": len(projects),
                "tasks_indexed": len(tasks)
            }
            
        except Exception as e:
            current_app.logger.error(f"خطأ في فهرسة المؤسسة: {str(e)}")
            return None
    
    def semantic_search(self, query, filters=None, limit=10):
        """بحث دلالي متقدم"""
        try:
            # بناء شروط البحث
            search_query = query
            
            if filters:
                filter_str = " AND ".join([f"{k}:{v}" for k, v in filters.items()])
                search_query = f"{query} {filter_str}"
            
            # تنفيذ البحث
            results = self.app.search(search_query, limit=limit)
            
            # تنسيق النتائج
            formatted_results = []
            for result in results:
                formatted_results.append({
                    "id": result.get("id"),
                    "text": result.get("text"),
                    "score": result.get("score"),
                    "metadata": result.get("metadata", {}),
                    "tags": result.get("tags", [])
                })
            
            return formatted_results
            
        except Exception as e:
            current_app.logger.error(f"خطأ في البحث الدلالي: {str(e)}")
            return []
    
    def find_similar_projects(self, project_id, limit=5):
        """إيجاد مشاريع مشابهة"""
        try:
            project = Project.query.get(project_id)
            if not project:
                return []
            
            # إنشاء متجه للمشروع
            query = f"{project.name} {project.description or ''} {project.site_name or ''}"
            
            # بحث عن مشاريع مشابهة
            results = self.app.search(query, limit=limit + 1)
            
            # استبعاد المشروع نفسه
            similar = []
            for result in results:
                if result.get("metadata", {}).get("id") != project_id:
                    similar.append(result)
                    if len(similar) >= limit:
                        break
            
            return similar
            
        except Exception as e:
            current_app.logger.error(f"خطأ في إيجاد مشاريع مشابهة: {str(e)}")
            return []
    
    def get_project_recommendations(self, user_id):
        """توصيات مشاريع لمستخدم"""
        try:
            user = User.query.get(user_id)
            if not user:
                return []
            
            # بناء استعلام بناءً على دور المستخدم
            query = f"role:{user.role} department:{user.dept_id}"
            
            if user.job_title:
                query += f" {user.job_title}"
            
            # بحث عن مشاريع مناسبة
            results = self.app.search(query, limit=10)
            
            return results
            
        except Exception as e:
            current_app.logger.error(f"خطأ في توصيات المشاريع: {str(e)}")
            return []
    
    def cluster_projects(self, n_clusters=5):
        """تجميع المشاريع في مجموعات متشابهة"""
        try:
            # الحصول على جميع مشاريع المؤسسة
            projects = Project.query.filter_by(org_id=self.org_id).all()
            
            # إنشاء نصوص للتجميع
            texts = []
            ids = []
            
            for project in projects:
                text = f"{project.name} {project.description or ''} {project.site_name or ''}"
                texts.append(text)
                ids.append(project.id)
            
            # تنفيذ التجميع
            clusters = self.app.cluster(texts, n_clusters)
            
            # تنسيق النتائج
            result = []
            for i, cluster_id in enumerate(clusters):
                result.append({
                    "project_id": ids[i],
                    "cluster": int(cluster_id),
                    "text": texts[i][:100]
                })
            
            return result
            
        except Exception as e:
            current_app.logger.error(f"خطأ في تجميع المشاريع: {str(e)}")
            return []