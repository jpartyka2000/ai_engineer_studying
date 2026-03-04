"""
Management command to seed initial visual topics.

This command:
1. Enables supports_visuals=True for all active subjects
2. Creates sample visual topics for Git, scikit-learn, transformers, LightGBM, and System Design
"""

from django.core.management.base import BaseCommand

from apps.subjects.models import Subject
from apps.visuals.models import VisualTopic


class Command(BaseCommand):
    """Seed visual topics for subjects with visual support."""

    help = "Seed initial visual topics and enable visuals for all subjects"

    def handle(self, *args, **options):
        """Execute the command."""
        self.stdout.write("Enabling visuals for all active subjects...")
        self.enable_visuals_for_all_subjects()

        self.stdout.write("Seeding visual topics...")
        self.seed_git_visuals()
        self.seed_sklearn_visuals()
        self.seed_transformers_visuals()
        self.seed_lightgbm_visuals()
        self.seed_system_design_visuals()

        self.stdout.write(self.style.SUCCESS("Successfully seeded visual topics!"))

    def enable_visuals_for_all_subjects(self):
        """Enable supports_visuals for all active subjects."""
        count = Subject.objects.filter(is_active=True).update(supports_visuals=True)
        self.stdout.write(f"  Enabled visuals for {count} subjects")

    def get_or_create_subject(self, name: str, slug: str, category: str) -> Subject:
        """Get or create a subject by slug."""
        subject, created = Subject.objects.get_or_create(
            slug=slug,
            defaults={
                "name": name,
                "category": category,
                "description": f"Learn {name} concepts",
                "supports_visuals": True,
            },
        )
        if not subject.supports_visuals:
            subject.supports_visuals = True
            subject.save(update_fields=["supports_visuals"])
        return subject

    def seed_git_visuals(self):
        """Seed Git visual topics."""
        subject = self.get_or_create_subject("Git", "git", "DevOps & Tooling")

        # Git Branches and HEAD
        topic, created = VisualTopic.objects.update_or_create(
            subject=subject,
            slug="git-branches-head",
            defaults={
                "title": "Git Branches and HEAD",
                "description": "Learn how Git branches work and what the HEAD pointer means",
                "rendering_type": VisualTopic.RenderingType.MERMAID,
                "difficulty": "beginner",
                "estimated_time_minutes": 5,
                "tags": ["git", "branches", "HEAD", "version-control"],
                "status": VisualTopic.Status.PUBLISHED,
                "source": "manual",
                "steps": [
                    {
                        "step_number": 0,
                        "title": "Initial Repository",
                        "explanation": "A new Git repository starts with a single commit on the `main` branch. **HEAD** is a special pointer that tells Git which branch (and commit) you're currently working on.",
                        "diagram_data": 'gitGraph\n    commit id: "C0" tag: "HEAD -> main"',
                    },
                    {
                        "step_number": 1,
                        "title": "Adding Commits",
                        "explanation": "Each new commit you make gets added to the current branch. The branch pointer (`main`) moves forward to the new commit, and HEAD follows along since it points to the branch.",
                        "diagram_data": 'gitGraph\n    commit id: "C0"\n    commit id: "C1"\n    commit id: "C2" tag: "HEAD -> main"',
                    },
                    {
                        "step_number": 2,
                        "title": "Creating a Branch",
                        "explanation": "When you create a new branch with `git branch feature`, Git creates a new pointer at the current commit. However, HEAD still points to `main` - you haven't switched branches yet.",
                        "diagram_data": 'gitGraph\n    commit id: "C0"\n    commit id: "C1"\n    commit id: "C2" tag: "main, feature"\n    branch feature',
                    },
                    {
                        "step_number": 3,
                        "title": "Switching Branches (Checkout)",
                        "explanation": "Running `git checkout feature` (or `git switch feature`) moves HEAD to point to the `feature` branch. Your working directory now reflects the state of that branch.",
                        "diagram_data": 'gitGraph\n    commit id: "C0"\n    commit id: "C1"\n    commit id: "C2" tag: "main"\n    branch feature\n    checkout feature\n    commit id: "" tag: "HEAD -> feature"',
                    },
                    {
                        "step_number": 4,
                        "title": "Working on Feature Branch",
                        "explanation": "Now when you make commits, they go on the `feature` branch. The `main` branch stays where it was. This is how Git enables parallel development.",
                        "diagram_data": 'gitGraph\n    commit id: "C0"\n    commit id: "C1"\n    commit id: "C2" tag: "main"\n    branch feature\n    checkout feature\n    commit id: "C3"\n    commit id: "C4" tag: "HEAD -> feature"',
                    },
                    {
                        "step_number": 5,
                        "title": "Merging Branches",
                        "explanation": "When your feature is complete, you can merge it back into `main`. First checkout main, then run `git merge feature`. Git creates a merge commit that combines both histories.",
                        "diagram_data": 'gitGraph\n    commit id: "C0"\n    commit id: "C1"\n    commit id: "C2"\n    branch feature\n    checkout feature\n    commit id: "C3"\n    commit id: "C4"\n    checkout main\n    merge feature id: "C5" tag: "HEAD -> main"',
                    },
                ],
            },
        )
        self.stdout.write(f"  {'Created' if created else 'Updated'}: {topic.title}")

    def seed_sklearn_visuals(self):
        """Seed scikit-learn visual topics."""
        subject = self.get_or_create_subject(
            "scikit-learn", "scikit-learn", "ML Frameworks"
        )

        # Decision Tree Training
        topic, created = VisualTopic.objects.update_or_create(
            subject=subject,
            slug="decision-tree-training",
            defaults={
                "title": "Decision Tree Training Process",
                "description": "Visualize how a Decision Tree classifier learns from data by finding optimal splits",
                "rendering_type": VisualTopic.RenderingType.MERMAID,
                "difficulty": "intermediate",
                "estimated_time_minutes": 8,
                "tags": ["decision-tree", "classification", "supervised-learning"],
                "status": VisualTopic.Status.PUBLISHED,
                "source": "manual",
                "steps": [
                    {
                        "step_number": 0,
                        "title": "Training Data",
                        "explanation": "We start with labeled training data. Our goal is to find **decision rules** (splits) that separate the data into pure groups based on the target labels.",
                        "diagram_data": 'graph TB\n    subgraph Training Data\n    A["X=[2,3], y=0 (Blue)"]\n    B["X=[4,5], y=1 (Red)"]\n    C["X=[1,2], y=0 (Blue)"]\n    D["X=[5,4], y=1 (Red)"]\n    E["X=[3,1], y=0 (Blue)"]\n    end',
                    },
                    {
                        "step_number": 1,
                        "title": "Root Node - All Data",
                        "explanation": "The tree starts with a **root node** containing all training samples. We need to find the best feature and threshold to split this data. The goal is to create child nodes that are more 'pure' (contain mostly one class).",
                        "diagram_data": 'graph TB\n    Root["Root Node<br/>5 samples<br/>3 Blue, 2 Red<br/>Impurity: 0.48"]',
                    },
                    {
                        "step_number": 2,
                        "title": "Evaluating Split Candidates",
                        "explanation": "For each feature, we try different **threshold values** and calculate the **information gain** (or Gini reduction). The split that best separates the classes wins.",
                        "diagram_data": 'graph TB\n    Root["Root: 5 samples"]\n    Root --> |"Try: X1 < 3.5"| Split1["Left: 3 samples<br/>Right: 2 samples"]\n    Root --> |"Try: X2 < 2.5"| Split2["Left: 2 samples<br/>Right: 3 samples"]\n    Split1 --> Best["Best Split!<br/>Gini Gain: 0.32"]\n    style Best fill:#90EE90',
                    },
                    {
                        "step_number": 3,
                        "title": "First Split Applied",
                        "explanation": "We apply the best split `X1 < 3.5`. Samples with X1 < 3.5 go left, others go right. The left node is now **pure** (all Blue), but the right still needs splitting.",
                        "diagram_data": 'graph TB\n    Root["X1 < 3.5?"]\n    Root -->|Yes| Left["3 samples<br/>3 Blue, 0 Red<br/>PURE!"]\n    Root -->|No| Right["2 samples<br/>0 Blue, 2 Red<br/>PURE!"]\n    style Left fill:#ADD8E6\n    style Right fill:#FFB6C1',
                    },
                    {
                        "step_number": 4,
                        "title": "Stopping Criteria",
                        "explanation": "A node becomes a **leaf** when: (1) it's pure (all same class), (2) max depth reached, (3) min samples threshold, or (4) no split improves purity. Leaf nodes make predictions.",
                        "diagram_data": 'graph TB\n    Root["X1 < 3.5?"]\n    Root -->|Yes| Left["Predict: Blue<br/>Confidence: 100%"]\n    Root -->|No| Right["Predict: Red<br/>Confidence: 100%"]\n    style Left fill:#ADD8E6\n    style Right fill:#FFB6C1',
                    },
                    {
                        "step_number": 5,
                        "title": "Making Predictions",
                        "explanation": "To predict a new sample, start at the root and follow the decision path. At each node, go left or right based on the split condition until you reach a leaf.",
                        "diagram_data": 'graph TB\n    New["New Sample<br/>X=[2.5, 3]"]\n    New --> Root["X1 < 3.5?"]\n    Root -->|"2.5 < 3.5? Yes!"| Left["Predict: Blue"]\n    Root -.->|No| Right["Predict: Red"]\n    style New fill:#FFFACD\n    style Left fill:#ADD8E6',
                    },
                ],
            },
        )
        self.stdout.write(f"  {'Created' if created else 'Updated'}: {topic.title}")

    def seed_transformers_visuals(self):
        """Seed Transformers visual topics."""
        subject = self.get_or_create_subject(
            "Transformers", "transformers", "Deep Learning"
        )

        # Self-Attention Mechanism
        topic, created = VisualTopic.objects.update_or_create(
            subject=subject,
            slug="self-attention",
            defaults={
                "title": "Self-Attention Mechanism",
                "description": "Step-by-step visualization of how self-attention works in transformers",
                "rendering_type": VisualTopic.RenderingType.MERMAID,
                "difficulty": "advanced",
                "estimated_time_minutes": 12,
                "tags": ["attention", "transformers", "nlp", "deep-learning"],
                "status": VisualTopic.Status.PUBLISHED,
                "source": "manual",
                "steps": [
                    {
                        "step_number": 0,
                        "title": "Input Embeddings",
                        "explanation": "Each token in the input sequence is converted to an **embedding vector**. These embeddings capture semantic meaning and are the starting point for attention computation.",
                        "diagram_data": 'graph LR\n    subgraph Input Tokens\n    T1[The]\n    T2[cat]\n    T3[sat]\n    end\n    subgraph Embeddings dim=4\n    E1["[0.1, 0.2, 0.3, 0.4]"]\n    E2["[0.5, 0.6, 0.7, 0.8]"]\n    E3["[0.2, 0.3, 0.4, 0.5]"]\n    end\n    T1 --> E1\n    T2 --> E2\n    T3 --> E3',
                    },
                    {
                        "step_number": 1,
                        "title": "Query, Key, Value Projections",
                        "explanation": "Each embedding is projected into three vectors: **Query (Q)**, **Key (K)**, and **Value (V)** using learned weight matrices. Q asks 'what am I looking for?', K says 'what do I contain?', V says 'what information do I provide?'",
                        "diagram_data": 'graph TB\n    E["Embedding"]\n    E --> |"W_Q"| Q["Query (Q)"]\n    E --> |"W_K"| K["Key (K)"]\n    E --> |"W_V"| V["Value (V)"]\n    style Q fill:#FFB6C1\n    style K fill:#ADD8E6\n    style V fill:#90EE90',
                    },
                    {
                        "step_number": 2,
                        "title": "Computing Attention Scores",
                        "explanation": "For each token, we compute how much it should 'attend' to every other token by taking the **dot product** of its Query with all Keys. Higher scores mean stronger attention.",
                        "diagram_data": 'graph TB\n    subgraph "Query from \'cat\'"\n    Q2["Q_cat"]\n    end\n    subgraph Keys\n    K1["K_The"]\n    K2["K_cat"]\n    K3["K_sat"]\n    end\n    Q2 --> |"Q·K = 0.3"| K1\n    Q2 --> |"Q·K = 0.8"| K2\n    Q2 --> |"Q·K = 0.5"| K3',
                    },
                    {
                        "step_number": 3,
                        "title": "Softmax Normalization",
                        "explanation": "The raw scores are scaled by √d_k (dimension of keys) and passed through **softmax** to get attention weights that sum to 1. This creates a probability distribution over tokens.",
                        "diagram_data": 'graph LR\n    subgraph Raw Scores\n    S1["0.3"]\n    S2["0.8"]\n    S3["0.5"]\n    end\n    subgraph Softmax Weights\n    W1["0.20"]\n    W2["0.45"]\n    W3["0.35"]\n    end\n    S1 --> |softmax| W1\n    S2 --> |softmax| W2\n    S3 --> |softmax| W3\n    Note["Sum = 1.0"]',
                    },
                    {
                        "step_number": 4,
                        "title": "Weighted Sum of Values",
                        "explanation": "The final output for each position is a **weighted sum** of all Value vectors, using the attention weights. Tokens with higher attention weights contribute more to the output.",
                        "diagram_data": 'graph TB\n    subgraph Values\n    V1["V_The"]\n    V2["V_cat"]\n    V3["V_sat"]\n    end\n    subgraph Weights\n    W1["0.20"]\n    W2["0.45"]\n    W3["0.35"]\n    end\n    Output["Output = 0.20·V_The + 0.45·V_cat + 0.35·V_sat"]\n    V1 --> |"× 0.20"| Output\n    V2 --> |"× 0.45"| Output\n    V3 --> |"× 0.35"| Output\n    style Output fill:#FFFACD',
                    },
                    {
                        "step_number": 5,
                        "title": "Multi-Head Attention",
                        "explanation": "In practice, we run **multiple attention heads** in parallel, each with its own Q, K, V projections. This allows the model to attend to different types of information simultaneously.",
                        "diagram_data": 'graph TB\n    Input["Input Embeddings"]\n    Input --> H1["Head 1<br/>Syntax?"]\n    Input --> H2["Head 2<br/>Semantics?"]\n    Input --> H3["Head 3<br/>Position?"]\n    H1 --> Concat["Concatenate"]\n    H2 --> Concat\n    H3 --> Concat\n    Concat --> Output["Final Output"]\n    style H1 fill:#FFB6C1\n    style H2 fill:#ADD8E6\n    style H3 fill:#90EE90',
                    },
                ],
            },
        )
        self.stdout.write(f"  {'Created' if created else 'Updated'}: {topic.title}")

    def seed_lightgbm_visuals(self):
        """Seed LightGBM visual topics."""
        subject = self.get_or_create_subject("LightGBM", "lightgbm", "ML Frameworks")

        # Leaf-wise Tree Growth
        topic, created = VisualTopic.objects.update_or_create(
            subject=subject,
            slug="lightgbm-leaf-wise-growth",
            defaults={
                "title": "LightGBM Leaf-wise Tree Growth",
                "description": "See how LightGBM builds trees using leaf-wise (best-first) growth strategy",
                "rendering_type": VisualTopic.RenderingType.MERMAID,
                "difficulty": "advanced",
                "estimated_time_minutes": 10,
                "tags": ["lightgbm", "gradient-boosting", "tree-algorithms"],
                "status": VisualTopic.Status.PUBLISHED,
                "source": "manual",
                "steps": [
                    {
                        "step_number": 0,
                        "title": "Initial Prediction",
                        "explanation": "LightGBM starts with an **initial prediction** for all samples, typically the mean of target values. This becomes the baseline that subsequent trees will improve upon.",
                        "diagram_data": 'graph TB\n    Root["Initial Prediction<br/>F_0 = mean(y) = 0.5<br/>100 samples"]\n    style Root fill:#E6E6FA',
                    },
                    {
                        "step_number": 1,
                        "title": "Calculate Residuals",
                        "explanation": "For each sample, calculate the **residual** (error): actual value minus current prediction. These residuals become the target for the next tree to learn.",
                        "diagram_data": 'graph TB\n    subgraph Current State\n    P["Predictions: 0.5 for all"]\n    end\n    subgraph Residuals\n    R1["Sample 1: 0.8 - 0.5 = 0.3"]\n    R2["Sample 2: 0.2 - 0.5 = -0.3"]\n    R3["Sample 3: 0.9 - 0.5 = 0.4"]\n    Rn["..."]\n    end\n    P --> R1\n    P --> R2\n    P --> R3',
                    },
                    {
                        "step_number": 2,
                        "title": "Find Best Split (Root)",
                        "explanation": "Unlike level-wise growth (XGBoost), LightGBM uses **leaf-wise** growth. It finds the leaf with the **highest potential gain** and splits that leaf, regardless of tree depth.",
                        "diagram_data": 'graph TB\n    Root["Root: All Samples<br/>Find best split across all features<br/>Best: feature_3 < 0.7<br/>Gain: 125.4"]\n    Root --> |"< 0.7"| L1["Left Leaf<br/>40 samples<br/>Potential Gain: 45.2"]\n    Root --> |">= 0.7"| R1["Right Leaf<br/>60 samples<br/>Potential Gain: 78.1"]\n    style Root fill:#90EE90\n    style R1 fill:#FFFACD',
                    },
                    {
                        "step_number": 3,
                        "title": "Split Leaf with Highest Gain",
                        "explanation": "LightGBM picks the leaf with highest potential gain (Right Leaf: 78.1) and splits it. This **greedy approach** often leads to deeper, more accurate trees than level-wise growth.",
                        "diagram_data": 'graph TB\n    Root["feature_3 < 0.7"]\n    Root --> L1["Left Leaf<br/>40 samples"]\n    Root --> R1["feature_1 < 2.3"]\n    R1 --> |"Split!"| RL["30 samples<br/>Gain: 52.3"]\n    R1 --> RR["30 samples<br/>Gain: 38.7"]\n    style R1 fill:#90EE90\n    style RL fill:#FFFACD',
                    },
                    {
                        "step_number": 4,
                        "title": "Continue Leaf-wise Growth",
                        "explanation": "This process continues: evaluate all current leaves, pick the one with highest gain, and split it. The tree grows asymmetrically, focusing on areas with most error.",
                        "diagram_data": 'graph TB\n    Root["feature_3 < 0.7"]\n    Root --> L1["Leaf: 40 samples"]\n    Root --> R1["feature_1 < 2.3"]\n    R1 --> RL["feature_5 < 1.1"]\n    R1 --> RR["Leaf: 30 samples"]\n    RL --> RLL["Leaf: 15 samples"]\n    RL --> RLR["Leaf: 15 samples"]\n    style RL fill:#90EE90',
                    },
                    {
                        "step_number": 5,
                        "title": "Stopping and Predictions",
                        "explanation": "Tree growth stops when: max leaves reached, max depth hit, or min gain threshold. Each leaf predicts a value to **reduce residuals**. The learning rate scales these predictions.",
                        "diagram_data": 'graph TB\n    Root["Tree Complete"]\n    Root --> L1["Predict: +0.15"]\n    Root --> R1["Split Node"]\n    R1 --> RL["Split Node"]\n    R1 --> RR["Predict: -0.22"]\n    RL --> RLL["Predict: +0.31"]\n    RL --> RLR["Predict: +0.08"]\n    Update["F_1 = F_0 + lr × tree_predictions"]\n    style Update fill:#E6E6FA',
                    },
                    {
                        "step_number": 6,
                        "title": "Ensemble of Trees",
                        "explanation": "LightGBM builds many trees sequentially. Each new tree fits the residuals from all previous trees. The final prediction is the sum of initial value plus all tree contributions.",
                        "diagram_data": 'graph LR\n    F0["F_0<br/>Initial"]\n    T1["Tree 1"]\n    T2["Tree 2"]\n    Tn["Tree N"]\n    Final["Final Prediction<br/>F_0 + lr×T1 + lr×T2 + ... + lr×TN"]\n    F0 --> |+| T1\n    T1 --> |+| T2\n    T2 --> |+| Tn\n    Tn --> Final\n    style Final fill:#90EE90',
                    },
                ],
            },
        )
        self.stdout.write(f"  {'Created' if created else 'Updated'}: {topic.title}")

    def seed_system_design_visuals(self):
        """Seed System Design visual topics."""
        subject = self.get_or_create_subject(
            "System Design", "system-design", "Architecture"
        )

        # ML Model Serving
        topic, created = VisualTopic.objects.update_or_create(
            subject=subject,
            slug="ml-model-serving-architecture",
            defaults={
                "title": "ML Model Serving Architecture",
                "description": "Learn the components of a production ML model serving system",
                "rendering_type": VisualTopic.RenderingType.MERMAID,
                "difficulty": "intermediate",
                "estimated_time_minutes": 8,
                "tags": ["system-design", "mlops", "serving", "architecture"],
                "status": VisualTopic.Status.PUBLISHED,
                "source": "manual",
                "steps": [
                    {
                        "step_number": 0,
                        "title": "Client Request",
                        "explanation": "A prediction request starts from a **client** (web app, mobile app, or internal service). The request contains input features needed for the model to make a prediction.",
                        "diagram_data": 'graph LR\n    Client["Client App"]\n    Client --> |"POST /predict<br/>{features: [...]}"| API["API Gateway"]\n    style Client fill:#ADD8E6\n    style API fill:#E6E6FA',
                    },
                    {
                        "step_number": 1,
                        "title": "API Gateway & Load Balancer",
                        "explanation": "The **API Gateway** handles authentication, rate limiting, and request validation. A **Load Balancer** distributes traffic across multiple model servers for high availability.",
                        "diagram_data": 'graph LR\n    Client["Clients"]\n    Client --> GW["API Gateway<br/>Auth, Rate Limit"]\n    GW --> LB["Load Balancer"]\n    LB --> S1["Server 1"]\n    LB --> S2["Server 2"]\n    LB --> S3["Server 3"]\n    style GW fill:#FFB6C1\n    style LB fill:#90EE90',
                    },
                    {
                        "step_number": 2,
                        "title": "Feature Store Lookup",
                        "explanation": "The model server may need additional features from a **Feature Store**. This provides precomputed features (user history, aggregations) that aren't in the request.",
                        "diagram_data": 'graph TB\n    Req["Request: user_id=123"]\n    Req --> Server["Model Server"]\n    Server --> |"Get features"| FS["Feature Store<br/>(Redis/Feast)"]\n    FS --> |"user_embedding,<br/>purchase_history"| Server\n    style FS fill:#FFFACD',
                    },
                    {
                        "step_number": 3,
                        "title": "Preprocessing Pipeline",
                        "explanation": "Raw features go through a **preprocessing pipeline**: normalization, encoding, missing value handling. This must match exactly what was used during training.",
                        "diagram_data": 'graph LR\n    Raw["Raw Features"]\n    Raw --> Norm["Normalize<br/>Numerical"]\n    Norm --> Enc["Encode<br/>Categorical"]\n    Enc --> Fill["Fill<br/>Missing"]\n    Fill --> Vec["Feature<br/>Vector"]\n    style Vec fill:#90EE90',
                    },
                    {
                        "step_number": 4,
                        "title": "Model Inference",
                        "explanation": "The preprocessed features are passed to the **ML model** for inference. The model is loaded in memory (or accessed via a serving framework like TensorFlow Serving, Triton, or custom).",
                        "diagram_data": 'graph TB\n    Features["Feature Vector"]\n    Features --> Model["ML Model<br/>(In Memory)"]\n    Model --> |"Inference"| Pred["Prediction<br/>score: 0.87"]\n    Cache["Model Cache<br/>Version: v2.3"]\n    Cache -.-> Model\n    style Model fill:#ADD8E6\n    style Pred fill:#90EE90',
                    },
                    {
                        "step_number": 5,
                        "title": "Postprocessing & Response",
                        "explanation": "The raw prediction may need **postprocessing**: applying thresholds, formatting output, adding explanations. The final response is sent back through the API.",
                        "diagram_data": 'graph LR\n    Pred["Raw: 0.87"]\n    Pred --> Post["Postprocess<br/>threshold > 0.5"]\n    Post --> Format["Format<br/>Response"]\n    Format --> Resp["{<br/>prediction: \'positive\',<br/>confidence: 0.87<br/>}"]\n    style Resp fill:#90EE90',
                    },
                    {
                        "step_number": 6,
                        "title": "Logging & Monitoring",
                        "explanation": "Every prediction is **logged** for debugging, monitoring, and model retraining. Metrics like latency, throughput, and prediction distribution are tracked.",
                        "diagram_data": 'graph TB\n    Server["Model Server"]\n    Server --> Log["Prediction Logs<br/>(input, output, latency)"]\n    Server --> Metrics["Metrics<br/>(Prometheus)"]\n    Log --> DW["Data Warehouse<br/>(Retraining)"]\n    Metrics --> Alert["Alerting<br/>(PagerDuty)"]\n    Metrics --> Dash["Dashboard<br/>(Grafana)"]\n    style Log fill:#FFFACD\n    style Metrics fill:#E6E6FA',
                    },
                ],
            },
        )
        self.stdout.write(f"  {'Created' if created else 'Updated'}: {topic.title}")
