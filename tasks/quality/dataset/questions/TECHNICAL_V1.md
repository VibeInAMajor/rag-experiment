# External retrieval questions — technical V1

**Created:** 2026-11-24  
**Updated:** 2026-11-24  
**Status:** Source-anchored open diagnostic set; human review and blind holdout pending.

Use only [corpus](../README.md) documents as retrieval inputs. Do not index these questions or their answers. Each family has three language-equivalent variants; the family is the independent sampling/split unit, not each translation. Questions are corpus-relative, not assertions about the latest product version. Query IDs are stable; separate answer key in [technical answers](../answers/TECHNICAL_V1.md).

| Query ID | Family | Language | Intent | Query |
| --- | --- | --- | --- | --- |
| EXT-K8S-001-EN | EXT-K8S-001 | EN | definition | What is the smallest deployable unit in Kubernetes, and what resources can its containers share? |
| EXT-K8S-001-RU | EXT-K8S-001 | RU | definition | Какая наименьшая единица развёртывания в Kubernetes и какие ресурсы разделяют её контейнеры? |
| EXT-K8S-001-UK | EXT-K8S-001 | UK | definition | Яка найменша одиниця розгортання в Kubernetes та які ресурси спільні для її контейнерів? |
| EXT-K8S-002-EN | EXT-K8S-002 | EN | failure | What does a workload controller do when a node hosting a Pod fails? |
| EXT-K8S-002-RU | EXT-K8S-002 | RU | failure | Что делает контроллер рабочей нагрузки при отказе узла с Pod? |
| EXT-K8S-002-UK | EXT-K8S-002 | UK | failure | Що робить контролер робочого навантаження, коли вузол із Pod виходить з ладу? |
| EXT-K8S-003-EN | EXT-K8S-003 | EN | causal | Does changing a workload's Pod template patch existing Pods in place? |
| EXT-K8S-003-RU | EXT-K8S-003 | RU | causal | Изменение шаблона Pod рабочей нагрузки обновляет существующие Pod на месте? |
| EXT-K8S-003-UK | EXT-K8S-003 | UK | causal | Чи змінює оновлення шаблону Pod уже наявні Pod на місці? |
| EXT-K8S-004-EN | EXT-K8S-004 | EN | definition | Which objects does a Kubernetes Deployment update declaratively? |
| EXT-K8S-004-RU | EXT-K8S-004 | RU | definition | Какие объекты Deployment обновляет декларативно? |
| EXT-K8S-004-UK | EXT-K8S-004 | UK | definition | Які об'єкти Deployment оновлює декларативно? |
| EXT-K8S-005-EN | EXT-K8S-005 | EN | causal | How does a Deployment replace Pods after its PodTemplateSpec changes? |
| EXT-K8S-005-RU | EXT-K8S-005 | RU | causal | Как Deployment заменяет Pod после изменения PodTemplateSpec? |
| EXT-K8S-005-UK | EXT-K8S-005 | UK | causal | Як Deployment замінює Pod після зміни PodTemplateSpec? |
| EXT-K8S-006-EN | EXT-K8S-006 | EN | configuration | Which Deployment field specifies the desired Pod replica count? |
| EXT-K8S-006-RU | EXT-K8S-006 | RU | configuration | Какое поле Deployment задаёт желаемое число реплик Pod? |
| EXT-K8S-006-UK | EXT-K8S-006 | UK | configuration | Яке поле Deployment задає бажану кількість реплік Pod? |
| EXT-K8S-007-EN | EXT-K8S-007 | EN | configuration | If a Service does not specify targetPort, what value is used? |
| EXT-K8S-007-RU | EXT-K8S-007 | RU | configuration | Какое значение получает targetPort Service, если его не указать? |
| EXT-K8S-007-UK | EXT-K8S-007 | UK | configuration | Яке значення має targetPort Service, якщо його не вказано? |
| EXT-K8S-008-EN | EXT-K8S-008 | EN | troubleshooting | Why are EndpointSlices not created automatically for a Service without a selector, and what must be done? |
| EXT-K8S-008-RU | EXT-K8S-008 | RU | troubleshooting | Почему EndpointSlice для Service без selector не создаются автоматически и что нужно сделать? |
| EXT-K8S-008-UK | EXT-K8S-008 | UK | troubleshooting | Чому EndpointSlice для Service без selector не створюються автоматично та що слід зробити? |
| EXT-K8S-009-EN | EXT-K8S-009 | EN | identifier | What label links a manually created EndpointSlice to its Service? |
| EXT-K8S-009-RU | EXT-K8S-009 | RU | identifier | Какая метка связывает вручную созданный EndpointSlice с Service? |
| EXT-K8S-009-UK | EXT-K8S-009 | UK | identifier | Яка мітка пов'язує створений вручну EndpointSlice із Service? |
| EXT-K8S-010-EN | EXT-K8S-010 | EN | numeric | What is the maximum data size of a ConfigMap? |
| EXT-K8S-010-RU | EXT-K8S-010 | RU | numeric | Каков максимальный объём данных ConfigMap? |
| EXT-K8S-010-UK | EXT-K8S-010 | UK | numeric | Який максимальний обсяг даних ConfigMap? |
| EXT-K8S-011-EN | EXT-K8S-011 | EN | multi-facet | How do ConfigMap updates differ for normal volume projection, environment variables, and subPath mounts? |
| EXT-K8S-011-RU | EXT-K8S-011 | RU | multi-facet | Чем отличаются обновления ConfigMap при обычном монтировании тома, переменных окружения и subPath? |
| EXT-K8S-011-UK | EXT-K8S-011 | UK | multi-facet | Чим відрізняються оновлення ConfigMap для звичайного монтування тому, змінних середовища та subPath? |
| EXT-K8S-012-EN | EXT-K8S-012 | EN | negation | Can an immutable ConfigMap be made mutable again without replacing it? |
| EXT-K8S-012-RU | EXT-K8S-012 | RU | negation | Можно ли снова сделать immutable ConfigMap изменяемым без пересоздания? |
| EXT-K8S-012-UK | EXT-K8S-012 | UK | negation | Чи можна зробити immutable ConfigMap змінним знову без його повторного створення? |
| EXT-K8S-013-EN | EXT-K8S-013 | EN | causal | What does a startup probe delay, and what happens if it fails? |
| EXT-K8S-013-RU | EXT-K8S-013 | RU | causal | Какие проверки откладывает startup probe и что происходит при её неудаче? |
| EXT-K8S-013-UK | EXT-K8S-013 | UK | causal | Які перевірки відкладає startup probe і що відбувається в разі її невдачі? |
| EXT-K8S-014-EN | EXT-K8S-014 | EN | multi-facet | What is the different operational consequence of a liveness failure versus a readiness failure? |
| EXT-K8S-014-RU | EXT-K8S-014 | RU | multi-facet | Чем различаются последствия провала liveness и readiness? |
| EXT-K8S-014-UK | EXT-K8S-014 | UK | multi-facet | Чим відрізняються наслідки невдалої liveness і readiness? |
| EXT-K8S-015-EN | EXT-K8S-015 | EN | causal | Why can a poorly designed liveness probe cause cascading failures during high load? |
| EXT-K8S-015-RU | EXT-K8S-015 | RU | causal | Почему неправильно настроенная liveness probe может вызвать каскадный сбой под нагрузкой? |
| EXT-K8S-015-UK | EXT-K8S-015 | UK | causal | Чому неправильно налаштована liveness probe може спричинити каскадний збій під навантаженням? |
| EXT-K8S-016-EN | EXT-K8S-016 | EN | cross-language | According to the Russian Pod documentation, can containers in the same Pod reach one another over localhost? |
| EXT-K8S-016-RU | EXT-K8S-016 | RU | cross-language | Согласно русской документации о Pod, могут ли контейнеры одного Pod связываться через localhost? |
| EXT-K8S-016-UK | EXT-K8S-016 | UK | cross-language | Згідно з російськомовною документацією про Pod, чи можуть контейнери одного Pod спілкуватися через localhost? |
| EXT-K8S-017-EN | EXT-K8S-017 | EN | cross-language | In the Ukrainian ConfigMap article, what does envFrom with configMapRef select? |
| EXT-K8S-017-RU | EXT-K8S-017 | RU | cross-language | В украинской статье о ConfigMap что выбирает envFrom с configMapRef? |
| EXT-K8S-017-UK | EXT-K8S-017 | UK | cross-language | В українській статті про ConfigMap що вибирає envFrom із configMapRef? |
| EXT-K8S-018-EN | EXT-K8S-018 | EN | cross-language | According to the Ukrainian ConfigMap article, how can an individual key be selected and renamed for a Pod environment variable? |
| EXT-K8S-018-RU | EXT-K8S-018 | RU | cross-language | Согласно украинской статье о ConfigMap, как выбрать отдельный ключ и задать другое имя переменной окружения Pod? |
| EXT-K8S-018-UK | EXT-K8S-018 | UK | cross-language | Згідно з українською статтею про ConfigMap, як вибрати окремий ключ та задати інше ім'я змінної середовища Pod? |
| EXT-K8S-019-EN | EXT-K8S-019 | EN | multi-document | How do Deployment replacement and readiness probes work together during a rollout to control which Pods receive traffic? |
| EXT-K8S-019-RU | EXT-K8S-019 | RU | multi-document | Как замена Pod через Deployment и readiness probe вместе определяют, какие Pod получают трафик при rollout? |
| EXT-K8S-019-UK | EXT-K8S-019 | UK | multi-document | Як заміна Pod через Deployment і readiness probe разом визначають, які Pod отримують трафік під час rollout? |
| EXT-AZ-001-EN | EXT-AZ-001 | EN | definition | What is the primary purpose of Azure Virtual Network? |
| EXT-AZ-001-RU | EXT-AZ-001 | RU | definition | Для чего предназначена Azure Virtual Network? |
| EXT-AZ-001-UK | EXT-AZ-001 | UK | definition | Для чого призначена Azure Virtual Network? |
| EXT-AZ-002-EN | EXT-AZ-002 | EN | comparison | How do site-to-site VPN and Azure ExpressRoute differ in their network path? |
| EXT-AZ-002-RU | EXT-AZ-002 | RU | comparison | Чем site-to-site VPN отличается от Azure ExpressRoute по сетевому маршруту? |
| EXT-AZ-002-UK | EXT-AZ-002 | UK | comparison | Чим site-to-site VPN відрізняється від Azure ExpressRoute за мережевим шляхом? |
| EXT-AZ-003-EN | EXT-AZ-003 | EN | negation | Must a virtual network be divided into subnets by availability zone for a zonal VM? |
| EXT-AZ-003-RU | EXT-AZ-003 | RU | negation | Нужно ли делить virtual network на подсети по availability zones для zonal VM? |
| EXT-AZ-003-UK | EXT-AZ-003 | UK | negation | Чи потрібно ділити virtual network на підмережі за availability zones для zonal VM? |
| EXT-AZ-004-EN | EXT-AZ-004 | EN | comparison | How does GRS differ from GZRS in primary-region replication? |
| EXT-AZ-004-RU | EXT-AZ-004 | RU | comparison | Чем GRS отличается от GZRS в репликации первичного региона? |
| EXT-AZ-004-UK | EXT-AZ-004 | UK | comparison | Чим GRS відрізняється від GZRS у реплікації первинного регіону? |
| EXT-AZ-005-EN | EXT-AZ-005 | EN | configuration | Which redundancy options allow reading from a secondary region before failover? |
| EXT-AZ-005-RU | EXT-AZ-005 | RU | configuration | Какие варианты redundancy позволяют читать из вторичного региона до failover? |
| EXT-AZ-005-UK | EXT-AZ-005 | UK | configuration | Які варіанти redundancy дозволяють читати з вторинного регіону до failover? |
| EXT-AZ-006-EN | EXT-AZ-006 | EN | causal | Why can loss of a primary Azure Storage region lead to data loss even with geo-replication, and what does RPO describe? |
| EXT-AZ-006-RU | EXT-AZ-006 | RU | causal | Почему при потере первичного региона Azure Storage возможна потеря данных даже с георепликацией и что показывает RPO? |
| EXT-AZ-006-UK | EXT-AZ-006 | UK | causal | Чому втрата первинного регіону Azure Storage може спричинити втрату даних навіть із геореплікацією та що описує RPO? |
| EXT-AZ-007-EN | EXT-AZ-007 | EN | multi-facet | What three elements make up an Azure RBAC role assignment? |
| EXT-AZ-007-RU | EXT-AZ-007 | RU | multi-facet | Из каких трёх элементов состоит Azure RBAC role assignment? |
| EXT-AZ-007-UK | EXT-AZ-007 | UK | multi-facet | З яких трьох елементів складається Azure RBAC role assignment? |
| EXT-AZ-008-EN | EXT-AZ-008 | EN | hierarchy | At which four levels can Azure RBAC scope be assigned? |
| EXT-AZ-008-RU | EXT-AZ-008 | RU | hierarchy | На каких четырёх уровнях можно назначить scope Azure RBAC? |
| EXT-AZ-008-UK | EXT-AZ-008 | UK | hierarchy | На яких чотирьох рівнях можна призначити scope Azure RBAC? |
| EXT-AZ-009-EN | EXT-AZ-009 | EN | causal | How is access granted and revoked through an Azure role assignment? |
| EXT-AZ-009-RU | EXT-AZ-009 | RU | causal | Как предоставляется и отзывается доступ через Azure role assignment? |
| EXT-AZ-009-UK | EXT-AZ-009 | UK | causal | Як надається та відкликається доступ через Azure role assignment? |
| EXT-AZ-010-EN | EXT-AZ-010 | EN | definition | What is Azure Resource Manager responsible for? |
| EXT-AZ-010-RU | EXT-AZ-010 | RU | definition | За что отвечает Azure Resource Manager? |
| EXT-AZ-010-UK | EXT-AZ-010 | UK | definition | За що відповідає Azure Resource Manager? |
| EXT-AZ-011-EN | EXT-AZ-011 | EN | comparison | What does declarative infrastructure syntax describe, and which two Azure formats are examples? |
| EXT-AZ-011-RU | EXT-AZ-011 | RU | comparison | Что описывает декларативный синтаксис инфраструктуры и какие два формата Azure служат примерами? |
| EXT-AZ-011-UK | EXT-AZ-011 | UK | comparison | Що описує декларативний синтаксис інфраструктури та які два формати Azure є прикладами? |
| EXT-AZ-012-EN | EXT-AZ-012 | EN | multi-document | Does an RBAC assignment scoped to one resource group inherently grant rights in a sibling group, and how does ARM scope inheritance explain it? |
| EXT-AZ-012-RU | EXT-AZ-012 | RU | multi-document | Даёт ли RBAC assignment в одной resource group права в соседней группе и как это объясняет наследование scope в ARM? |
| EXT-AZ-012-UK | EXT-AZ-012 | UK | multi-document | Чи надає RBAC assignment в одній resource group права в сусідній групі та як це пояснює успадкування scope в ARM? |
| EXT-CS-001-EN | EXT-CS-001 | EN | causal | What happens when an async method contains no await expression or statement? |
| EXT-CS-001-RU | EXT-CS-001 | RU | causal | Что происходит, если async-метод не содержит await? |
| EXT-CS-001-UK | EXT-CS-001 | UK | causal | Що відбувається, якщо async-метод не містить await? |
| EXT-CS-002-EN | EXT-CS-002 | EN | multi-facet | When should a C# async method return Task<TResult> rather than Task or void? |
| EXT-CS-002-RU | EXT-CS-002 | RU | multi-facet | Когда async-метод C# должен возвращать Task<TResult>, а не Task или void? |
| EXT-CS-002-UK | EXT-CS-002 | UK | multi-facet | Коли async-метод C# має повертати Task<TResult>, а не Task або void? |
| EXT-CS-003-EN | EXT-CS-003 | EN | causal | Does await block the evaluating thread, and what if the awaited operation is already complete? |
| EXT-CS-003-RU | EXT-CS-003 | RU | causal | Блокирует ли await выполняющий поток и что происходит, если операция уже завершилась? |
| EXT-CS-003-UK | EXT-CS-003 | UK | causal | Чи блокує await потік виконання та що стається, якщо операція вже завершена? |
| EXT-CS-004-EN | EXT-CS-004 | EN | code | What does await t yield for Task<T> compared with Task, and how are exceptions handled? |
| EXT-CS-004-RU | EXT-CS-004 | RU | code | Что возвращает await t для Task<T> и Task и что происходит с исключением? |
| EXT-CS-004-UK | EXT-CS-004 | UK | code | Що повертає await t для Task<T> і Task та що відбувається з винятком? |
| EXT-CS-005-EN | EXT-CS-005 | EN | code | Which C# statements consume asynchronous streams and asynchronously disposable objects? |
| EXT-CS-005-RU | EXT-CS-005 | RU | code | Какие операторы C# применяются для асинхронных потоков и асинхронно освобождаемых объектов? |
| EXT-CS-005-UK | EXT-CS-005 | UK | code | Які оператори C# застосовуються для асинхронних потоків та асинхронно звільнюваних об'єктів? |
| EXT-CS-006-EN | EXT-CS-006 | EN | comparison | Which C# record declarations are reference types and which are value types? |
| EXT-CS-006-RU | EXT-CS-006 | RU | comparison | Какие объявления record в C# являются ссылочными, а какие значимыми типами? |
| EXT-CS-006-UK | EXT-CS-006 | UK | comparison | Які оголошення record у C# є посилальними, а які типами значень? |
| EXT-CS-007-EN | EXT-CS-007 | EN | comparison | Are positional record properties mutable in record class, readonly record struct, and record struct? |
| EXT-CS-007-RU | EXT-CS-007 | RU | comparison | Изменяемы ли позиционные свойства record class, readonly record struct и record struct? |
| EXT-CS-007-UK | EXT-CS-007 | UK | comparison | Чи змінювані позиційні властивості record class, readonly record struct і record struct? |
| EXT-CS-008-EN | EXT-CS-008 | EN | causal | Why can generic collections be safer and more efficient for value types than nongeneric collections? |
| EXT-CS-008-RU | EXT-CS-008 | RU | causal | Почему generic-коллекции могут быть безопаснее и эффективнее для value types, чем негeneric-коллекции? |
| EXT-CS-008-UK | EXT-CS-008 | UK | causal | Чому generic-колекції можуть бути безпечнішими й ефективнішими для типів значень, ніж негeneric-колекції? |
| EXT-CS-009-EN | EXT-CS-009 | EN | comparison | What is the difference between generic covariance and contravariance in C#? |
| EXT-CS-009-RU | EXT-CS-009 | RU | comparison | Чем различаются covariance и contravariance у generic-типов C#? |
| EXT-CS-009-UK | EXT-CS-009 | UK | comparison | Чим відрізняються covariance і contravariance в generic-типах C#? |
| EXT-CS-010-EN | EXT-CS-010 | EN | comparison | How is a LINQ query over IEnumerable<T> executed differently from IQueryable<T>? |
| EXT-CS-010-RU | EXT-CS-010 | RU | comparison | Чем выполнение LINQ-запроса над IEnumerable<T> отличается от IQueryable<T>? |
| EXT-CS-010-UK | EXT-CS-010 | UK | comparison | Чим виконання LINQ-запиту над IEnumerable<T> відрізняється від IQueryable<T>? |
| EXT-CS-011-EN | EXT-CS-011 | EN | code | Which LINQ query-expression keywords correspond to Select and Where? |
| EXT-CS-011-RU | EXT-CS-011 | RU | code | Какие ключевые слова LINQ query expression соответствуют Select и Where? |
| EXT-CS-011-UK | EXT-CS-011 | UK | code | Які ключові слова LINQ query expression відповідають Select і Where? |
| EXT-CS-012-EN | EXT-CS-012 | EN | code | What happens to a try block with neither catch nor finally, and when does finally execute? |
| EXT-CS-012-RU | EXT-CS-012 | RU | code | Что происходит с try без catch и finally и когда выполняется finally? |
| EXT-CS-012-UK | EXT-CS-012 | UK | code | Що відбувається з try без catch і finally та коли виконується finally? |
| EXT-CS-013-EN | EXT-CS-013 | EN | troubleshooting | Why should more derived exception catch blocks precede base-class catches? |
| EXT-CS-013-RU | EXT-CS-013 | RU | troubleshooting | Почему catch для производных исключений должен стоять перед catch базового класса? |
| EXT-CS-013-UK | EXT-CS-013 | UK | troubleshooting | Чому catch для похідних винятків має стояти перед catch базового класу? |
| EXT-CS-014-EN | EXT-CS-014 | EN | multi-document | Why is async void generally unsuitable for a method whose caller must observe its errors, compared with an awaited Task? |
| EXT-CS-014-RU | EXT-CS-014 | RU | multi-document | Почему async void обычно не подходит, если вызывающему коду нужно наблюдать ошибки, по сравнению с awaited Task? |
| EXT-CS-014-UK | EXT-CS-014 | UK | multi-document | Чому async void зазвичай не підходить, якщо викликач має спостерігати помилки, порівняно з awaited Task? |
