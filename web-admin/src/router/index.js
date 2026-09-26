import { createRouter, createWebHashHistory } from 'vue-router'
import {
  DataAnalysis, DataLine, Document, Files, Grid, Notebook, PriceTag, Setting, Tickets, Upload, User, UserFilled,
  CircleCheck, Lock, View, List, Histogram, DocumentChecked, Reading, Files as FilesIcon, DataBoard, EditPen,
  MagicStick, Key,
} from '@element-plus/icons-vue'

const AdminLayout = () => import('../layouts/AdminLayout.vue')

export const routes = [
  {
    path: '/login',
    name: 'login',
    component: () => import('../views/Login.vue'),
    meta: { title: '管理员登录', hidden: true, public: true },
  },
  {
    path: '/',
    component: AdminLayout,
    redirect: '/dashboard',
    children: [
      {
        path: 'dashboard',
        name: 'dashboard',
        component: () => import('../views/Dashboard.vue'),
        meta: { title: '数据看板', icon: DataAnalysis, perm: 'dashboard.view', group: 'overview' },
      },
      {
        path: 'ai-usage',
        name: 'ai-usage',
        component: () => import('../views/AIUsageAnalytics.vue'),
        meta: { title: 'AI使用分析', icon: MagicStick, perm: 'dashboard.view', group: 'overview' },
      },
      {
        path: 'users',
        name: 'users',
        component: () => import('../views/Users.vue'),
        meta: { title: '用户管理', icon: UserFilled, perm: 'user.view', group: 'content' },
      },
      {
        path: 'users/:openid/profile',
        name: 'user-profile',
        component: () => import('../views/UserProfile.vue'),
        meta: { title: '用户画像', hidden: true, perm: 'user.view' },
      },
      {
        path: 'questions',
        name: 'questions',
        component: () => import('../views/Questions.vue'),
        meta: { title: '题库管理', icon: Tickets, perm: 'question.view', group: 'content' },
      },
      {
        path: 'import',
        name: 'import',
        component: () => import('../views/Import.vue'),
        meta: { title: '批量导入', icon: Upload, perm: 'question.import', group: 'content' },
      },
      {
        path: 'tags',
        name: 'tags',
        component: () => import('../views/Tags.vue'),
        meta: { title: '标签管理', icon: PriceTag, perm: 'tag.view', group: 'content' },
      },
      {
        path: 'subjects',
        name: 'subjects',
        component: () => import('../views/Subjects.vue'),
        meta: { title: '科目管理', icon: Grid, perm: 'subject.view', group: 'content' },
      },
      {
        path: 'exams',
        name: 'exams',
        component: () => import('../views/Exams.vue'),
        meta: { title: '考试管理', icon: Files, perm: 'exam.view', group: 'content' },
      },
      {
        path: 'knowledge',
        name: 'knowledge',
        component: () => import('../views/Knowledge.vue'),
        meta: { title: '知识库管理', icon: Reading, perm: 'knowledge.view', group: 'content' },
      },
      {
        path: 'articles',
        name: 'articles',
        component: () => import('../views/Articles.vue'),
        meta: { title: '文章管理', icon: Document, perm: 'article.view', group: 'content' },
      },
      {
        path: 'articles/create',
        name: 'article-create',
        component: () => import('../views/ArticleEdit.vue'),
        meta: { title: '新建文章', hidden: true, perm: 'article.manage' },
      },
      {
        path: 'articles/:id/edit',
        name: 'article-edit',
        component: () => import('../views/ArticleEdit.vue'),
        meta: { title: '编辑文章', hidden: true, perm: 'article.manage' },
      },
      {
        path: 'records',
        name: 'records',
        component: () => import('../views/Records.vue'),
        meta: { title: '答题记录', icon: Document, perm: 'record.view', group: 'data' },
      },
      {
        path: 'notes',
        name: 'notes',
        component: () => import('../views/Notes.vue'),
        meta: { title: '错题笔记', icon: Notebook, perm: 'note.view', group: 'data' },
      },
      {
        path: 'studynotes',
        name: 'studynotes',
        component: () => import('../views/StudyNotes.vue'),
        meta: { title: '学习笔记', icon: EditPen, perm: 'studynote.view', group: 'data' },
      },
      {
        path: 'data',
        name: 'data',
        component: () => import('../views/DataBrowser.vue'),
        meta: { title: '数据浏览', icon: DataLine, perm: 'data.view', group: 'data' },
      },
      {
        path: 'ai-config',
        name: 'ai-config',
        component: () => import('../views/AIConfig.vue'),
        meta: { title: 'AI配置', icon: Setting, perm: 'ai.config', group: 'system' },
      },
      {
        path: 'ai-compose',
        name: 'ai-compose',
        component: () => import('../views/AICompose.vue'),
        meta: { title: 'AI智能组卷', icon: Files, perm: 'ai.compose', group: 'system' },
      },
      {
        path: 'ai-grading',
        name: 'ai-grading',
        component: () => import('../views/AIGrading.vue'),
        meta: { title: 'AI判卷复核', icon: DocumentChecked, perm: 'ai.grade', group: 'system' },
      },
      {
        path: 'ai-exam-analysis',
        name: 'ai-exam-analysis',
        component: () => import('../views/AIExamAnalysis.vue'),
        meta: { title: 'AI试卷分析', icon: Histogram, perm: 'ai.report', group: 'system' },
      },
      {
        path: 'ai-excel-validate',
        name: 'ai-excel-validate',
        component: () => import('../views/AIExcelValidate.vue'),
        meta: { title: 'AI数据校验', icon: CircleCheck, perm: 'question.import', group: 'system' },
      },
      {
        path: 'app-settings',
        name: 'app-settings',
        component: () => import('../views/AppSettings.vue'),
        meta: { title: '应用设置', icon: Setting, perm: 'admin.view', group: 'system' },
      },
      {
        path: 'activation-codes',
        name: 'activation-codes',
        component: () => import('../views/ActivationCodes.vue'),
        meta: { title: '激活码管理', icon: Key, perm: 'admin.view', group: 'system' },
      },
      {
        path: 'system',
        name: 'system',
        redirect: '/system/admins',
        meta: { title: '系统管理', icon: Setting, perm: 'admin.view', group: 'system' },
        children: [
          {
            path: 'admins',
            name: 'admins',
            component: () => import('../views/Admins.vue'),
            meta: { title: '管理员账号', icon: User, perm: 'admin.view' },
          },
          {
            path: 'roles',
            name: 'roles',
            component: () => import('../views/Roles.vue'),
            meta: { title: '角色权限', icon: Lock, perm: 'admin.view' },
          },
          {
            path: 'logs',
            name: 'logs',
            component: () => import('../views/Logs.vue'),
            meta: { title: '操作日志', icon: List, perm: 'admin.view' },
          },
        ],
      },
      {
        path: 'profile',
        name: 'profile',
        component: () => import('../views/Profile.vue'),
        meta: { title: '账号设置', hidden: true },
      },
      {
        path: 'forbidden',
        name: 'forbidden',
        component: () => import('../views/Forbidden.vue'),
        meta: { title: '无访问权限', hidden: true },
      },
    ],
  },
  {
    path: '/:pathMatch(.*)*',
    name: 'not-found',
    component: () => import('../views/NotFound.vue'),
    meta: { title: '页面不存在', hidden: true, public: true },
  },
]

// 侧边栏分组配置
export const navGroups = [
  { key: 'overview', label: '概览' },
  { key: 'content', label: '内容管理' },
  { key: 'data', label: '数据中心' },
  { key: 'system', label: '系统设置' },
]

const router = createRouter({
  history: createWebHashHistory(),
  routes,
})

router.beforeEach(async (to) => {
  const { useUserStore } = await import('../stores/user')
  const store = useUserStore()

  if (to.meta.public) return true

  if (!store.token) {
    return { name: 'login', query: { redirect: to.fullPath } }
  }
  if (!store.profile) {
    try {
      await store.fetchProfile()
    } catch (e) {
      return { name: 'login' }
    }
  }
  if (to.meta.perm && !store.hasPerm(to.meta.perm)) {
    return { name: 'forbidden' }
  }
  return true
})

export default router
