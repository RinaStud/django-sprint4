from django.contrib.auth import get_user_model, login
from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.core.paginator import Paginator
from django.utils import timezone

from .forms import UserRegistrationForm, PostForm, CommentForm, UserProfileForm
from .models import Category, Post, Comment


PAGE = 10
User = get_user_model()


def filter_posts(**kwargs):
    """Фильтрация постов."""
    return Post.objects.select_related(
        'category', 'location', 'author'
    ).filter(**kwargs).order_by('-pub_date')


def paginated_view(request, queryset, items_per_page=PAGE):
    """Пагинация."""
    paginator = Paginator(queryset, items_per_page)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    return page_obj


def index(request):
    """Главная страница."""
    all_posts = filter_posts(
        is_published=True,
        category__is_published=True,
        pub_date__lte=timezone.now()
    )

    page_obj = paginated_view(request, all_posts, items_per_page=PAGE)
    return render(
        request,
        'blog/index.html',
        {'page_obj': page_obj}
    )


def post_detail(request, post_id):
    """Детальный просмотр публикации."""
    post = get_object_or_404(Post, pk=post_id)
    now = timezone.now()

    can_view = False
    if post.is_published and post.pub_date <= now and (
        post.category is None or post.category.is_published
    ):
        can_view = True
    elif request.user.is_authenticated and post.author == request.user:
        can_view = True
    elif request.user.is_authenticated and request.user.is_staff:
        can_view = True

    if not can_view:
        raise Http404("Если пользователь не может видеть пост.")

    comments = post.comments.all().select_related(
        'author'
    )
    form = CommentForm()

    context = {
        'post': post,
        'comments': comments,
        'form': form,
        'now': now
    }
    return render(request, 'blog/detail.html', context)


def category_posts(request, category_slug):
    """Просмотр категории публикации."""
    category = get_object_or_404(
        Category,
        slug=category_slug,
        is_published=True
    )
    now = timezone.now()
    all_category_posts = filter_posts(
        is_published=True,
        pub_date__lte=timezone.now(),
        category=category
    )

    visible_posts = []
    for post in all_category_posts:
        can_view_post = False
        # Условия, при которых пост виден:
        # 1. Пост опубликован для всех
        if post.is_published and post.pub_date <= now and (
            post.category is None or post.category.is_published
        ):
            can_view_post = True
        # 2. Пользователь является автором поста
        elif request.user.is_authenticated and post.author == request.user:
            can_view_post = True
        # 3. Пользователь является администратором
        elif request.user.is_authenticated and request.user.is_staff:
            can_view_post = True

        if can_view_post:
            visible_posts.append(post)

    page_obj = paginated_view(request, visible_posts, items_per_page=PAGE)

    return render(
        request,
        'blog/category.html',
        {'category': category, 'page_obj': page_obj}
    )


def registration(request):
    """Регистрация пользователя."""
    if request.method == 'POST':
        form = UserRegistrationForm(request.POST or None)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect('blog:profile')
    else:
        form = UserRegistrationForm()
    return render(
        request,
        'registration/registration_form.html',
        {'form': form}
    )


def profile_view(request, username):
    """Детальный просмотр профиля пользователя."""
    user_obj = get_object_or_404(User, username=username)
    posts = Post.objects.filter(author=user_obj)
    page_obj = paginated_view(request, posts, items_per_page=PAGE)
    return render(
        request, 'blog/profile.html',
        {'profile': user_obj, 'page_obj': page_obj}
    )


@login_required
def edit_profile(request):
    """Редактирование профиля."""
    if request.method == 'POST':
        form = UserProfileForm(request.POST or None, instance=request.user)
        if form.is_valid():
            form.save()
            return redirect('blog:profile', username=request.user.username)
    else:
        form = UserProfileForm(instance=request.user)

    context = {
        'form': form,
    }
    return render(request, 'blog/user.html', context)


# ПОСТЫ
@login_required
def create_post(request):
    """Создание публикации."""
    if request.method == 'POST':
        form = PostForm(request.POST or None, request.FILES or None)
        if form.is_valid():
            post = form.save(commit=False)
            post.author = request.user
            post.is_published = True
            if not post.pub_date:
                post.pub_date = timezone.now()
            post.save()
            return redirect('blog:profile', username=request.user.username)
    else:
        form = PostForm()
    return render(
        request, 'blog/create.html',
        {'form': form}
    )


@login_required
def edit_post(request, post_id):
    """Редактирование публикации."""
    post = get_object_or_404(Post, pk=post_id)
    if post.author != request.user:
        return redirect('blog:post_detail', post_id=post.id)

    if request.method == 'POST':
        form = PostForm(request.POST, files=request.FILES, instance=post)
        if form.is_valid():
            saved_post = form.save()
            return redirect('blog:post_detail', post_id=saved_post.id)
    else:
        form = PostForm(instance=post)
    return render(request, 'blog/create.html', {'form': form})


@login_required
def delete_post(request, post_id):
    """Удаление публикации."""
    post = get_object_or_404(Post, id=post_id)
    if post.author != request.user:
        return redirect('blog:post_detail', post_id=post.id)

    if request.method == 'POST':
        post.delete()
        return redirect('blog:profile', username=request.user.username)

    context = {
        'post': post,
    }
    return render(request, 'blog/create.html', context)


# КОММЕНТЫ
@login_required
def add_comment(request, post_id):
    """Добавление коммента к публикации."""
    post = get_object_or_404(Post, id=post_id)

    if request.method == 'POST':
        form = CommentForm(request.POST)
        if form.is_valid():
            comment = form.save(commit=False)
            comment.post = post
            comment.author = request.user
            comment.save()
            return redirect('blog:post_detail', post_id=post.id)
    else:
        form = CommentForm()

    return render(
        request,
        'blog/comment.html',
        {'post': post, 'form': form}
    )


@login_required
def edit_comment(request, post_id, comment_id):
    """Редактирование коммента к публикации."""
    comment = get_object_or_404(Comment, pk=comment_id, post__pk=post_id)
    if comment.author != request.user:
        return HttpResponseForbidden()

    if request.method == 'POST':
        form = CommentForm(request.POST or None, instance=comment)
        if form.is_valid():
            comment = form.save(commit=False)
            comment.is_published = True
            comment.save()
            return redirect('blog:post_detail', post_id=post_id)
    else:
        form = CommentForm(instance=comment)

    context = {
        'form': form,
        'comment': comment,
        'post': comment.post,
    }
    return render(request, 'blog/comment.html', context)


@login_required
def delete_comment(request, post_id, comment_id):
    """Удаление коммента к публикации."""
    comment = get_object_or_404(Comment, pk=comment_id, post__pk=post_id)
    if comment.author != request.user:
        return HttpResponseForbidden()

    if request.method == 'POST':
        comment.delete()
        return redirect('blog:post_detail', post_id=post_id)

    context = {
        'comment': comment,
        'post': comment.post,
    }
    return render(request, 'blog/comment.html', context)
