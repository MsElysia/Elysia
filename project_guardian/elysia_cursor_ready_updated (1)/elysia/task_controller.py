# task_controller.py

class TaskController:
    def __init__(self, router, evaluator, mutation_flow):
        self.router = router
        self.evaluator = evaluator
        self.mutation_flow = mutation_flow
        self.task_log = []

    def run_task(self, module_id, request, expected_keywords):
        output = self.router.receive_request(module_id, request)
        feedback = self.evaluator.score_response(
            prompt=request['goal'],
            response=output['response'],
            expected_keywords=expected_keywords
        )
        self.task_log.append({
            "request": request,
            "response": output,
            "feedback": feedback
        })
        return output, feedback
