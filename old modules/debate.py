import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

# Simulation Parameters
NUM_DEBATES = 100
INITIAL_TRUST = 75
BIG_FLOP_DECAY = 10  # Severe penalty if mediator input fails both DA & external check
MILD_STUMBLE_DECAY = 2  # Small penalty if mediator input fails DA but passes external
SUCCESS_REWARD = 1  # Small trust gain for validated input

# Adjustments at 50 cycles based on mediator input
TUNING_CYCLE = 50
AMBIGUOUS_PHASE = 25  # Last 25 rounds are ambiguous cases

# Generate random debate results (simulating reality)
np.random.seed(42)  # Ensuring reproducibility
debate_outcomes = np.random.choice(["perfect", "flawed"], size=TUNING_CYCLE, p=[0.5, 0.5])
ambiguous_outcomes = np.random.choice(["perfect", "flawed"], size=AMBIGUOUS_PHASE, p=[0.5, 0.5])

# Trust score tracking
trust_scores = [INITIAL_TRUST]
trust = INITIAL_TRUST

for i in range(NUM_DEBATES):
    if i < TUNING_CYCLE:
        outcome = debate_outcomes[i]
    else:
        outcome = ambiguous_outcomes[i - TUNING_CYCLE]  # Last 25 debates are ambiguous
    
    if outcome == "perfect":
        trust = min(100, trust + SUCCESS_REWARD)  # Prevent exceeding 100%
    elif outcome == "flawed":
        if np.random.rand() < 0.5:  # 50% chance it’s a big flop
            trust = max(0, trust - BIG_FLOP_DECAY)
        else:
            trust = max(0, trust - MILD_STUMBLE_DECAY)

    trust_scores.append(trust)

# Convert results into a dataframe for visualization
df = pd.DataFrame({"Debate Number": range(NUM_DEBATES+1), "Trust Score": trust_scores})

# Plot results
plt.figure(figsize=(10, 5))
plt.plot(df["Debate Number"], df["Trust Score"], marker="o", linestyle="-", color="blue")
plt.axvline(x=TUNING_CYCLE, color="red", linestyle="--", label="Tuning Point")
plt.xlabel("Debate Number")
plt.ylabel("Trust Score")
plt.title("Elysia's Trust Decay Simulation")
plt.legend()
plt.grid(True)

# Display the results
import ace_tools as tools
tools.display_dataframe_to_user(name="Trust Decay Simulation Results", dataframe=df)
plt.show()
