"""
primavera_engine.py - محرك الجدولة وحساب المسار الحرج
"""
from datetime import datetime, timedelta
from sqlalchemy import and_, or_
from app.models import db
from app.models import Activity, ActivityRelationship,Project,Baseline,WBS

class PrimaveraEngine:
    """محرك Primavera للجدولة وحساب المسار الحرج"""
    
    def __init__(self, project):
        self.project = project
        self.activities = []
        self.relationships = []
        
    def load_project_data(self):
        """تحميل بيانات المشروع"""
        self.activities = Activity.query.filter_by(
            project_id=self.project.id
        ).order_by(Activity.id).all()
        
        self.relationships = ActivityRelationship.query.filter_by(
            project_id=self.project.id
        ).all()
        
    def calculate_early_dates(self):
        """حساب التواريخ المبكرة (Forward Pass)"""
        activities_by_id = {a.id: a for a in self.activities}
        predecessors = {}
        
        for rel in self.relationships:
            if rel.successor_id not in predecessors:
                predecessors[rel.successor_id] = []
            predecessors[rel.successor_id].append(rel.predecessor_id)
        
        for activity in self.activities:
            if activity.id not in predecessors:
                activity.early_start = self.project.project.planned_start
                if activity.calendar:
                    activity.early_finish = activity.calendar.calculate_duration_days(
                        activity.early_start, activity.original_duration
                    )
                else:
                    activity.early_finish = activity.early_start + timedelta(days=activity.original_duration)
            else:
                max_finish = None
                for pred_id in predecessors[activity.id]:
                    pred = activities_by_id.get(pred_id)
                    if pred and pred.early_finish:
                        if not max_finish or pred.early_finish > max_finish:
                            max_finish = pred.early_finish
                
                if max_finish:
                    activity.early_start = max_finish
                    if activity.calendar:
                        activity.early_finish = activity.calendar.calculate_duration_days(
                            activity.early_start, activity.original_duration
                        )
                    else:
                        activity.early_finish = activity.early_start + timedelta(days=activity.original_duration)
        
        db.session.commit()
    
    def calculate_late_dates(self):
        """حساب التواريخ المتأخرة (Backward Pass)"""
        activities_by_id = {a.id: a for a in self.activities}
        successors = {}
        
        for rel in self.relationships:
            if rel.predecessor_id not in successors:
                successors[rel.predecessor_id] = []
            successors[rel.predecessor_id].append(rel.successor_id)
        
        # تحديد تاريخ انتهاء المشروع
        project_end = self.project.project.planned_finish
        if not project_end and self.activities:
            project_end = max(a.early_finish for a in self.activities if a.early_finish)
        
        # حساب التواريخ المتأخرة (من النهاية إلى البداية)
        for activity in reversed(self.activities):
            if activity.id not in successors:  # نشاط نهاية
                activity.late_finish = project_end
                if activity.calendar:
                    activity.late_start = activity.late_finish - timedelta(days=activity.original_duration)
                else:
                    activity.late_start = activity.late_finish - timedelta(days=activity.original_duration)
            else:
                # أقل تاريخ بدء للمهام التالية
                min_start = None
                for succ_id in successors[activity.id]:
                    succ = activities_by_id.get(succ_id)
                    if succ and succ.late_start:
                        if not min_start or succ.late_start < min_start:
                            min_start = succ.late_start
                
                if min_start:
                    activity.late_finish = min_start
                    if activity.calendar:
                        activity.late_start = activity.late_finish - timedelta(days=activity.original_duration)
                    else:
                        activity.late_start = activity.late_finish - timedelta(days=activity.original_duration)
        
        db.session.commit()
    
    def calculate_float(self):
        """حساب Float (الوقت السماحي)"""
        for activity in self.activities:
            if activity.late_start and activity.early_start:
                activity.total_float = (activity.late_start - activity.early_start).total_seconds() / (3600 * 24)
            else:
                activity.total_float = 0
            
            # المسار الحرج
            activity.is_critical = (activity.total_float == 0)
        
        db.session.commit()
    
    def get_critical_path(self):
        """الحصول على المسار الحرج"""
        critical_activities = [a for a in self.activities if a.is_critical]
        
        # ترتيب المسار الحرج
        path = []
        current = next((a for a in critical_activities if not self.has_predecessors_in_critical(a)), None)
        
        while current:
            path.append(current)
            next_activity = self.get_next_in_critical(current)
            current = next_activity
        
        return path
    
    def has_predecessors_in_critical(self, activity):
        """التحقق مما إذا كان للنشاط مهام سابقة في المسار الحرج"""
        for rel in self.relationships:
            if rel.successor_id == activity.id:
                pred = Activity.query.get(rel.predecessor_id)
                if pred and pred.is_critical:
                    return True
        return False
    
    def get_next_in_critical(self, activity):
        """الحصول على النشاط التالي في المسار الحرج"""
        for rel in self.relationships:
            if rel.predecessor_id == activity.id:
                succ = Activity.query.get(rel.successor_id)
                if succ and succ.is_critical:
                    return succ
        return None
    
    def run_schedule(self):
        """تشغيل الجدولة الكاملة"""
        self.load_project_data()
        self.calculate_early_dates()
        self.calculate_late_dates()
        self.calculate_float()
        
        # تحديث إحصائيات المشروع
        self.project.project.total_activities = len(self.activities)
        self.project.project.critical_activities = len([a for a in self.activities if a.is_critical])
        self.project.project.total_float = min((a.total_float for a in self.activities), default=0)
        
        if self.activities:
            self.project.project.planned_finish = max(a.early_finish for a in self.activities if a.early_finish)
        
        db.session.commit()
        
        return {
            'total_activities': self.project.project.total_activities,
            'critical_activities': self.project.project.critical_activities,
            'total_float': self.project.project.total_float,
            'project_duration': (self.project.project.planned_finish - self.project.project.planned_start).days if self.project.project.planned_finish else 0,
            'critical_path': [{'id': a.id, 'name': a.activity_name} for a in self.get_critical_path()]
        }
    
    def compare_with_baseline(self, baseline):
        """مقارنة التقدم مع خط الأساس"""
        comparison = {
            'schedule_variance': 0,
            'cost_variance': 0,
            'activities_ahead': 0,
            'activities_behind': 0,
            'activities_on_time': 0
        }
        
        for activity in self.activities:
            baseline_activity = next(
                (a for a in baseline.activities_snapshot if a['id'] == activity.id),
                None
            )
            
            if baseline_activity:
                # فرق الجدول الزمني
                if activity.actual_start and baseline_activity['planned_start']:
                    start_diff = (activity.actual_start - datetime.fromisoformat(baseline_activity['planned_start'])).days
                    if start_diff > 0:
                        comparison['activities_behind'] += 1
                        comparison['schedule_variance'] += start_diff
                    elif start_diff < 0:
                        comparison['activities_ahead'] += 1
                    else:
                        comparison['activities_on_time'] += 1
        
        return comparison


# ============================================
# دوال مساعدة للتكامل مع النظام الحالي
# ============================================

def convert_project_to_primavera(project):
    """تحويل مشروع عادي إلى مشروع Primavera"""
    primavera_project = Project(
        project_id=project.id,
        name=project.name,
        project_code=project.project_code,
        planned_start=project.planned_start_date,
        planned_finish=project.planned_end_date,
        created_by=project.created_by
    )
    db.session.add(primavera_project)
    db.session.flush()
    
    # إنشاء WBS رئيسي
    root_wbs = WBS(
        project_id=primavera_project.id,
        wbs_code='1',
        name='المشروع',
        level=1,
        wbs_path='1'
    )
    db.session.add(root_wbs)
    
    db.session.commit()
    return primavera_project


def create_baseline(project, name):
    """إنشاء خط أساس جديد"""
    activities = Activity.query.filter_by(project_id=project.id).all()
    
    baseline = Baseline(
        project_id=project.id,
        name=name,
        version=(Baseline.query.filter_by(project_id=project.id).count() + 1),
        created_by=project.created_by,
        activities_snapshot=[{
            'id': a.id,
            'activity_id': a.activity_id,
            'activity_name': a.activity_name,
            'planned_start': a.planned_start.isoformat() if a.planned_start else None,
            'planned_finish': a.planned_finish.isoformat() if a.planned_finish else None,
            'original_duration': a.original_duration
        } for a in activities],
        planned_start=project.project.planned_start,
        planned_finish=project.project.planned_finish
    )
    
    db.session.add(baseline)
    db.session.commit()
    
    return baseline