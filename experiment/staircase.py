class StairCase:
    def __init__(self, start: float, step:float, min_val: float, n_reversals: int, n_averaged: int):
        self.current = start
        self.step = step
        self.n_reversals = n_reversals
        self.n_averaged = n_averaged
        self.min_val = min_val

        self.reversals : list[float] = []
        self.consecutive_corrects : int = 0
        self.last_up : bool = True


    def is_done(self)->bool:
        return len(self.reversals) >= self.n_reversals
    
    def update(self, correct: bool):
        if(self.is_done()) : return 
        if correct: 
            if self.last_up:
                self.last_up = False
                self.reversals.append(self.current)
            self.consecutive_corrects+=1 
            if self.consecutive_corrects >= 2:
                self.current = max(self.current - self.step, self.min_val)
                self.consecutive_corrects = 0
            
        else:
            if not self.last_up:
                self.last_up = True
                self.reversals.append(self.current)
            self.current = self.current + self.step
            self.consecutive_corrects = 0
            

    def threshold(self) -> float:
        return sum(self.reversals[-self.n_averaged:]) / self.n_averaged