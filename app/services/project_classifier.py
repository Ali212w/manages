"""
نظام تصنيف المشاريع الذكي - يحدد نوع المشروع ومتطلباته تلقائياً
"""
import openai
from enum import Enum
from typing import Dict, Any, List
import json
import re

class ProjectDomain(Enum):
    """نطاقات المشاريع المدعومة"""
    CONSTRUCTION = "هندسي/إنشائي"
    SOFTWARE = "تقني/برمجيات"
    IT_INFRASTRUCTURE = "تقني/بنية تحتية"
    ADMINISTRATIVE = "إداري/تنظيمي"
    CREATIVE = "إبداعي/فني"
    RESEARCH = "بحثي/علمي"
    EDUCATIONAL = "تعليمي/تدريبي"
    AGRICULTURAL = "زراعي/غذائي"
    COMMERCIAL = "تجاري/تسويقي"
    HEALTHCARE = "صحي/طبي"
    INDUSTRIAL = "صناعي/تصنيعي"
    EVENT = "فعاليات/مؤتمرات"
    OTHER = "أخرى"

class ProjectClassifier:
    """مصنف المشاريع الذكي"""
    
    def __init__(self, api_key):
        openai.api_key = api_key
        
    def classify_project(self, text_content: str, filename: str = "") -> Dict[str, Any]:
        """
        تحديد نوع المشروع ومتطلباته من محتوى الملف
        """
        
        prompt = f"""
        أنت خبير في إدارة المشاريع بجميع أنواعها. قم بتحليل المحتوى التالي و:
        1. حدد نوع المشروع بدقة
        2. استخرج المجال الرئيسي
        3. حدد المنهجية المناسبة لإدارة هذا المشروع
        4. حدد المقاييس والمؤشرات المناسبة
        5. اقترح هيكل تقسيم العمل المناسب

        اسم الملف: {filename}
        المحتوى:
        {text_content[:4000]}

        قم بإرجاع النتيجة بصيغة JSON التالية:
        {{
            "domain": "نطاق المشروع",
            "subdomain": "التخصص الدقيق",
            "project_type": "نوع المشروع",
            "confidence": 0.95,
            "methodology": {{
                "primary": "المشروع أجيلي",
                "secondary": "المشروع تقليدي",
                "hybrid_approach": "وصف النهج المختلط"
            }},
            "key_metrics": [
                {{"name": "مقياس 1", "unit": "وحدة", "target": 100}},
                {{"name": "مقياس 2", "unit": "وحدة", "target": 50}}
            ],
            "wbs_structure": [
                {{"phase": "المرحلة 1", "deliverables": ["تسليم 1", "تسليم 2"]}},
                {{"phase": "المرحلة 2", "deliverables": ["تسليم 3", "تسليم 4"]}}
            ],
            "required_skills": ["مهارة 1", "مهارة 2"],
            "risk_categories": ["مخاطر تقنية", "مخاطر موارد"],
            "compliance_standards": ["معيار 1", "معيار 2"],
            "custom_fields": {{
                "field1": "قيمة مخصصة حسب نوع المشروع"
            }}
        }}
        """
        
        try:
            response = openai.ChatCompletion.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": "أنت خبير في تصنيف وإدارة جميع أنواع المشاريع."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                max_tokens=1500
            )
            
            result = response.choices[0].message.content
            result = self._clean_json(result)
            return json.loads(result)
            
        except Exception as e:
            print(f"Error in project classification: {e}")
            return self._default_classification(text_content)
    
    def _clean_json(self, text: str) -> str:
        """تنظيف استجابة JSON"""
        json_pattern = r'\{[\s\S]*\}'
        match = re.search(json_pattern, text)
        return match.group() if match else "{}"
    
    def _default_classification(self, text: str) -> Dict:
        """تصنيف افتراضي عند فشل API"""
        return {
            "domain": "غير محدد",
            "subdomain": "عام",
            "project_type": "مشروع عام",
            "confidence": 0.5,
            "methodology": {
                "primary": "PMBOK",
                "secondary": "مرن",
                "hybrid_approach": "نهج هجين حسب المتطلبات"
            },
            "key_metrics": [
                {"name": "نسبة الإنجاز", "unit": "%", "target": 100},
                {"name": "الالتزام بالجدول", "unit": "%", "target": 90},
                {"name": "الالتزام بالميزانية", "unit": "%", "target": 90}
            ],
            "wbs_structure": [
                {"phase": "التخطيط", "deliverables": ["خطة المشروع", "جدول زمني"]},
                {"phase": "التنفيذ", "deliverables": ["مخرجات المرحلة"]},
                {"phase": "المراجعة", "deliverables": ["تقرير نهائي"]}
            ],
            "required_skills": ["إدارة مشاريع", "تخطيط"],
            "risk_categories": ["فنية", "إدارية", "مالية"],
            "compliance_standards": ["ISO 21500"],
            "custom_fields": {}
        }

    def get_project_template(self, domain: str, project_type: str) -> Dict:
        """
        الحصول على قالب المشروع المناسب حسب النوع
        """
        templates = {
            "هندسي/إنشائي": {
                "wbs_template": "construction_wbs.json",
                "milestone_types": ["contractual", "technical", "administrative"],
                "activity_attributes": ["planned_quantity", "actual_quantity", "unit"],
                "resources": ["workers", "equipment", "materials"],
                "quality_checks": ["inspection", "testing", "approval"],
                "safety_requirements": True,
                "progress_measurement": "physical_percentage"
            },
            "تقني/برمجيات": {
                "wbs_template": "software_wbs.json",
                "milestone_types": ["sprint", "release", "deployment"],
                "activity_attributes": ["story_points", "effort_hours", "complexity"],
                "resources": ["developers", "designers", "testers"],
                "quality_checks": ["code_review", "testing", "user_acceptance"],
                "safety_requirements": False,
                "progress_measurement": "story_points_completed"
            },
            "إداري/تنظيمي": {
                "wbs_template": "administrative_wbs.json",
                "milestone_types": ["phase_completion", "approval", "launch"],
                "activity_attributes": ["documentation", "meetings", "approvals"],
                "resources": ["staff", "consultants", "trainers"],
                "quality_checks": ["audit", "review", "feedback"],
                "safety_requirements": False,
                "progress_measurement": "tasks_completed"
            },
            "بحثي/علمي": {
                "wbs_template": "research_wbs.json",
                "milestone_types": ["literature_review", "experiment", "publication"],
                "activity_attributes": ["samples", "experiments", "analyses"],
                "resources": ["researchers", "lab_equipment", "software"],
                "quality_checks": ["peer_review", "validation", "replication"],
                "safety_requirements": True,
                "progress_measurement": "experiments_completed"
            },
            "زراعي/غذائي": {
                "wbs_template": "agricultural_wbs.json",
                "milestone_types": ["planting", "irrigation", "harvest"],
                "activity_attributes": ["area", "quantity", "yield"],
                "resources": ["land", "seeds", "fertilizers", "workers"],
                "quality_checks": ["soil_test", "crop_inspection", "certification"],
                "safety_requirements": True,
                "progress_measurement": "area_cultivated"
            },
            "تجاري/تسويقي": {
                "wbs_template": "commercial_wbs.json",
                "milestone_types": ["campaign_launch", "market_entry", "sales_target"],
                "activity_attributes": ["budget", "reach", "conversion"],
                "resources": ["marketers", "designers", "budget"],
                "quality_checks": ["roi_analysis", "market_research", "customer_feedback"],
                "safety_requirements": False,
                "progress_measurement": "sales_achieved"
            }
        }
        
        return templates.get(domain, templates["إداري/تنظيمي"])