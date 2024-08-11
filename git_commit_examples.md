
# Git Commit Message Examples

## 1. `feat`（新增功能）
```
feat: add user profile page

Introduced a new user profile page accessible from the dashboard. The profile page allows users to update their personal information and preferences. This change also includes corresponding unit tests.
```

## 2. `fix`（修复 Bug）
```
fix: correct pagination logic in search results

Fixed an issue where the pagination was incorrectly displaying the total number of pages in search results. This was caused by a miscalculation in the results count after filtering was applied. Closes #342.
```

## 3. `docs`（文档变更）
```
docs: update API usage examples in README

Revised the API section of the README to reflect the latest changes in the authentication flow. Added detailed examples for better clarity. 
```

## 4. `style`（代码格式）
```
style: reformat codebase with Prettier

Reformatted the entire codebase using Prettier for consistent styling across the project. This includes adjusting indentation, line breaks, and other formatting rules. No functional changes were made.
```

## 5. `refactor`（重构代码）
```
refactor: optimize database queries in the user module

Refactored the user module to reduce the number of database queries. Consolidated multiple queries into a single optimized query to improve performance. This change should significantly reduce load times for user data retrieval.
```

## 6. `test`（增加测试）
```
test: add unit tests for the authentication middleware

Added a comprehensive suite of unit tests for the authentication middleware. These tests cover various scenarios, including valid and invalid tokens, expired sessions, and user role checks.
```

## 7. `chore`（构建过程或辅助工具的变动）
```
chore: update dependency versions

Updated several dependencies to their latest versions to keep the project up-to-date. This includes upgrading `express` to version 4.17.1 and `mongoose` to version 5.10.7. No breaking changes are expected.
```

## 8. `perf`（优化性能）
```
perf: improve image loading speed on homepage

Implemented lazy loading for images on the homepage to improve initial page load speed. This change should reduce the time it takes for the page to become interactive by deferring off-screen image loading until they are needed.
```

## 9. `ci`（持续集成相关的改动）
```
ci: configure Travis CI for automated testing

Added a `.travis.yml` file to configure Travis CI for automated testing of pull requests. This ensures that all code changes are automatically tested before merging.
```

## 10. `build`（影响构建系统或外部依赖的变更，例如 npm、webpack）
```
build: configure Webpack for production environment

Updated Webpack configuration to optimize for production builds. This includes enabling minification, tree-shaking, and code splitting to reduce the final bundle size.
```

## 11. `revert`（回滚之前的提交）
```
revert: revert "feat: add user profile page"

This reverts commit abcdef1234567890fedcba.
The new user profile page introduced several issues in the authentication flow. Rolling back to investigate and address these problems.
```

## 12. `hotfix`（紧急修复）
```
hotfix: fix critical bug causing server crash

Fixed a critical issue where the server would crash when processing certain types of requests. This fix was applied urgently to restore service. A more comprehensive fix will follow.
```
