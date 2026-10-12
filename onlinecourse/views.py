from django.shortcuts import render, get_object_or_404, redirect
from django.http import HttpResponseRedirect
from django.urls import reverse
from django.views import generic
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.models import User
from .models import Course, Enrollment, Question, Choice, Submission
import logging

logger = logging.getLogger(__name__)


def registration_request(request):
    context = {}

    if request.method == 'GET':
        return render(
            request,
            'onlinecourse/user_registration_bootstrap.html',
            context
        )

    if request.method == 'POST':
        username = request.POST.get('username', '')
        password = request.POST.get('psw', '')
        first_name = request.POST.get('firstname', '')
        last_name = request.POST.get('lastname', '')

        if User.objects.filter(username=username).exists():
            context['message'] = 'User already exists.'
            return render(
                request,
                'onlinecourse/user_registration_bootstrap.html',
                context
            )

        user = User.objects.create_user(
            username=username,
            password=password,
            first_name=first_name,
            last_name=last_name
        )

        login(request, user)
        return redirect('onlinecourse:index')


def login_request(request):
    context = {}

    if request.method == 'POST':
        username = request.POST.get('username', '')
        password = request.POST.get('psw', '')

        user = authenticate(
            request,
            username=username,
            password=password
        )

        if user is not None:
            login(request, user)
            return redirect('onlinecourse:index')

        context['message'] = 'Invalid username or password.'

    return render(
        request,
        'onlinecourse/user_login_bootstrap.html',
        context
    )


def logout_request(request):
    logout(request)
    return redirect('onlinecourse:index')


def check_if_enrolled(user, course):
    if not user.is_authenticated:
        return False

    return Enrollment.objects.filter(
        user=user,
        course=course
    ).exists()


class CourseListView(generic.ListView):
    template_name = 'onlinecourse/course_list_bootstrap.html'
    context_object_name = 'course_list'

    def get_queryset(self):
        courses = Course.objects.order_by('-total_enrollment')[:10]

        for course in courses:
            course.is_enrolled = check_if_enrolled(
                self.request.user,
                course
            )

        return courses


class CourseDetailView(generic.DetailView):
    model = Course
    template_name = 'onlinecourse/course_detail_bootstrap.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['is_enrolled'] = check_if_enrolled(
            self.request.user,
            self.object
        )
        return context


def enroll(request, course_id):
    if not request.user.is_authenticated:
        return redirect('onlinecourse:login')

    course = get_object_or_404(Course, pk=course_id)

    enrollment, created = Enrollment.objects.get_or_create(
        user=request.user,
        course=course,
        defaults={'mode': 'honor'}
    )

    if created:
        course.total_enrollment += 1
        course.save()

    return redirect(
        'onlinecourse:course_details',
        pk=course.id
    )


def extract_answers(request):
    answer_ids = []

    for key, value in request.POST.items():
        if key.startswith('choice_'):
            try:
                answer_ids.append(int(value))
            except (ValueError, TypeError):
                continue

    return answer_ids


def submit(request, course_id):
    if request.method != 'POST':
        return redirect(
            'onlinecourse:course_details',
            pk=course_id
        )

    if not request.user.is_authenticated:
        return redirect('onlinecourse:login')

    course = get_object_or_404(Course, pk=course_id)

    enrollment = Enrollment.objects.filter(
        user=request.user,
        course=course
    ).first()

    if enrollment is None:
        enrollment = Enrollment.objects.create(
            user=request.user,
            course=course,
            mode='honor'
        )

        course.total_enrollment += 1
        course.save()

    submission = Submission.objects.create(
        enrollment=enrollment
    )

    answer_ids = extract_answers(request)

    valid_choices = Choice.objects.filter(
        id__in=answer_ids,
        question__course=course
    )

    submission.choices.set(valid_choices)

    return redirect(
        'onlinecourse:show_exam_result',
        course_id=course.id,
        submission_id=submission.id
    )


def show_exam_result(request, course_id, submission_id):
    if not request.user.is_authenticated:
        return redirect('onlinecourse:login')

    course = get_object_or_404(Course, pk=course_id)

    submission = get_object_or_404(
        Submission,
        pk=submission_id,
        enrollment__course=course,
        enrollment__user=request.user
    )

    selected_choices = submission.choices.all()

    total_score = 0
    total_grade = 0
    question_results = []

    for question in course.question_set.all():
        total_grade += question.grade

        selected_for_question = selected_choices.filter(
            question=question
        )

        selected_ids = list(
            selected_for_question.values_list('id', flat=True)
        )

        has_correct_choice = question.choice_set.filter(
            is_correct=True
        ).exists()

        is_correct = (
            has_correct_choice
            and question.is_get_score(selected_ids)
            and not selected_for_question.filter(
                is_correct=False
            ).exists()
        )

        question_score = question.grade if is_correct else 0
        total_score += question_score

        question_results.append({
            'question': question,
            'selected_choices': selected_for_question,
            'is_correct': is_correct,
            'grade': question_score,
        })

    percentage = (
        (total_score / total_grade) * 100
        if total_grade > 0 else 0
    )

    passed = total_grade > 0 and percentage >= 50

    context = {
        'course': course,
        'submission': submission,
        'selected_choices': selected_choices,
        'question_results': question_results,
        'total_score': total_score,
        'total_grade': total_grade,
        'percentage': percentage,
        'grade': percentage,
        'passed': passed,
    }

    return render(
        request,
        'onlinecourse/exam_result_bootstrap.html',
        context
    )