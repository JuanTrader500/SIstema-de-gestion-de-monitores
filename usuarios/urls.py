from django.contrib.auth import views as auth_views
from django.urls import path

from . import views

urlpatterns = [
	path('login/', views.login_view, name='login'),
	path('router/', views.post_login_router, name='post_login_router'),
	path('admin/', views.admin_dashboard, name='admin_dashboard'),
	path('monitor/', views.monitor_dashboard, name='monitor_dashboard'),
	path('monitores/crear/', views.crear_monitor_view, name='crear_monitor'),
	path('api/chat/', views.ai_chat_api, name='ai_chat_api'),
	path('logout/', views.logout_view, name='logout'),
	path(
		'set-password/',
		views.CustomPasswordResetView.as_view(
			template_name='usuarios/password_reset_form.html',
			email_template_name='registration/password_reset_email.txt',
			html_email_template_name='registration/password_reset_email.html',
			subject_template_name='registration/password_reset_subject.txt',
		),
		name='password_reset',
	),
	path(
		'set-password/done/',
		auth_views.PasswordResetDoneView.as_view(
			template_name='usuarios/password_reset_done.html',
		),
		name='password_reset_done',
	),
	path(
		'set-password/<uidb64>/<token>/',
		auth_views.PasswordResetConfirmView.as_view(
			template_name='usuarios/set_password.html',
		),
		name='password_reset_confirm',
	),
	path(
		'set-password/complete/',
		auth_views.PasswordResetCompleteView.as_view(
			template_name='usuarios/password_reset_complete.html',
		),
		name='password_reset_complete',
	),
]
